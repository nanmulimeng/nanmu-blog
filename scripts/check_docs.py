"""Check repository documentation without network or application dependencies.

python scripts/check_docs.py
python scripts/check_docs.py --snippets --bash /path/to/bash --node /path/to/node
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SPEC = Path('docs/superpowers/specs/2026-10-02-nanmu-blog-design.md')
PLAN = Path('docs/superpowers/plans/2026-10-02-m0-blog-launch.md')


def split_markdown(text: str):
    """Yield prose lines and fenced blocks; respect fence length/indentation."""
    prose, blocks, body = [], [], []
    fence = None
    language = ''
    first = 0
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r'^\s*(`{3,}|~{3,})(.*)$', line)
        if fence is None and match:
            fence, language = match.group(1), match.group(2).strip()
            first, body = number, []
        elif fence and match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) and not match.group(2).strip():
            blocks.append((language, '\n'.join(body) + '\n', first))
            fence = None
        elif fence:
            body.append(line)
        else:
            prose.append((number, line))
    if fence:
        raise ValueError(f'unclosed fence at line {first}')
    return prose, blocks


def local_links(path: Path, prose):
    count, errors = 0, []
    for number, line in prose:
        line = re.sub(r'`+[^`]*`+', '', line)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', line):
            target = target.strip().strip('<>')
            if re.match(r'^[a-zA-Z][\w+.-]*:', target) or target.startswith('#'):
                continue
            target = unquote(target.split('#', 1)[0])
            if not target:
                continue
            count += 1
            if not (path.parent / target).exists():
                errors.append(f'{path.relative_to(ROOT)}:{number}: missing {target}')
    return count, errors


def schema_bodies(text: str):
    return [re.sub(r'\s+', '', body) for body in re.findall(r'schema: z\.object\(\{(.*?)\}\)', text, re.S)]


def duplicate_sections(text: str, prose):
    """Warn only for identical nonempty H2 sections outside fenced examples."""
    lines = text.splitlines()
    headings = [(number, line) for number, line in prose if line.startswith('## ')]
    seen, warnings = {}, []
    for index, (number, heading) in enumerate(headings):
        end = headings[index + 1][0] - 1 if index + 1 < len(headings) else len(lines)
        body = '\n'.join(lines[number:end]).strip()
        if not body:
            continue
        key = (heading, body)
        if key in seen:
            warnings.append(f'{seen[key]},{number}: duplicate complete section {heading}')
        else:
            seen[key] = number
    return warnings


def command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', timeout=30)
    if result.returncode:
        raise ValueError(f'{argv[0]} exited {result.returncode}: {result.stderr.strip()}')


def check_snippets(blocks, bash, node):
    bash = bash or shutil.which('bash')
    node = node or shutil.which('node')
    if not bash or not node:
        raise ValueError('--snippets requires Bash and Node; specify --bash/--node')
    counts = {'bash': 0, 'javascript': 0, 'json': 0, 'smoke_cases': 0}
    with tempfile.TemporaryDirectory(prefix='nanmu-docs-') as folder:
        tmp = Path(folder)
        smoke = None
        for index, (language, body, _) in enumerate(blocks):
            if language == 'bash' and body.startswith('#!/bin/bash'):
                path = tmp / f'snippet-{index}.sh'
                path.write_text(body, encoding='utf-8', newline='\n')
                command([bash, '-n', path.as_posix()])
                counts['bash'] += 1
            elif language == 'js':
                path = tmp / f'snippet-{index}.mjs'
                path.write_text(body, encoding='utf-8')
                command([node, '--check', str(path)])
                counts['javascript'] += 1
                if 'const mustExist' in body:
                    smoke = body
            elif language == 'json':
                body = body.strip()
                json.loads(body if body.startswith('{') else '{' + body + '}')
                counts['json'] += 1
        if counts['bash'] != 2 or smoke is None:
            raise ValueError('M0 plan must contain two deploy scripts and one smoke script')
        scripts = tmp / 'site/scripts'
        scripts.mkdir(parents=True)
        dist = tmp / 'site/dist'
        dist.mkdir()
        smoke_path = scripts / 'smoke.mjs'
        smoke_path.write_text(smoke, encoding='utf-8')
        for name in ['index.html', 'posts/index.html', 'digest/index.html', 'about/index.html', '404.html']:
            path = dist / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('<html><body>empty</body></html>', encoding='utf-8')
        xml = '<?xml version="1.0"?><rss><channel></channel></rss>'
        for name in ['rss.xml', 'digest.xml']:
            (dist / name).write_text(xml, encoding='utf-8')

        def smoke_case(success, label):
            result = subprocess.run([node, str(smoke_path)], capture_output=True, text=True, encoding='utf-8', timeout=30)
            passed = result.returncode == 0 if success else result.returncode != 0 and 'SMOKE FAIL' in result.stderr
            if not passed:
                raise ValueError(f'smoke case {label}: {result.stdout} {result.stderr}')
            counts['smoke_cases'] += 1

        smoke_case(True, 'complete empty site')
        (dist / 'digest.xml').unlink()
        smoke_case(False, 'missing feed')
        (dist / 'digest.xml').write_text(xml, encoding='utf-8')
        draft = dist / 'posts/drafts-example/index.html'
        draft.parent.mkdir()
        draft.write_text('draft', encoding='utf-8')
        smoke_case(False, 'draft detail')
        draft.unlink()
        draft.parent.rmdir()
        index = dist / 'index.html'
        index.write_text('<script>alert(1)</script>', encoding='utf-8')
        smoke_case(False, 'client script')
        index.write_text('<a href="/posts/drafts-example/">draft</a>', encoding='utf-8')
        smoke_case(False, 'draft link')
        index.write_text('<p>restored</p>', encoding='utf-8')
        smoke_case(True, 'restored')
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snippets', action='store_true', help='Also check M0 JS/Bash snippets and smoke fixtures in a temporary directory')
    parser.add_argument('--bash', help='Bash executable (Windows: use Git Bash, not the WSL launcher)')
    parser.add_argument('--node', help='Node executable')
    args = parser.parse_args()
    errors, warnings, parsed = [], [], {}
    links = 0
    paths = sorted(ROOT.glob('*.md')) + sorted((ROOT / 'docs').rglob('*.md'))
    for path in paths:
        try:
            source = path.read_text(encoding='utf-8')
            prose, blocks = split_markdown(source)
            parsed[path.relative_to(ROOT)] = blocks
            count, missing = local_links(path, prose)
            links += count
            errors.extend(missing)
            warnings.extend(f'{path.relative_to(ROOT)}:{item}' for item in duplicate_sections(source, prose))
        except (OSError, ValueError) as exc:
            errors.append(f'{path.relative_to(ROOT)}: {exc}')
    report = {'syntax_and_links': {'markdown_files': len(paths), 'local_links': links}, 'contracts': {}}
    try:
        spec = (ROOT / SPEC).read_text(encoding='utf-8')
        plan = (ROOT / PLAN).read_text(encoding='utf-8')
        schemas = schema_bodies(spec)
        if len(schemas) != 2 or schemas != schema_bodies(plan):
            raise ValueError('posts/digest schema examples differ between spec and M0 plan')
        sql = next(body for lang, body, _ in parsed[SPEC] if lang == 'sql')
        with sqlite3.connect(':memory:') as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.executescript(sql)
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {'entry', 'receipt', 'receipt_attempt', 'budget', 'analysis', 'override', 'digest_issue', 'api_usage'}
        if tables != expected:
            raise ValueError(f'unexpected engine tables: {sorted(tables)}')
        report['contracts']['ddl_tables'] = len(tables)
        report['contracts']['schema_examples_match'] = True
        if args.snippets:
            report['snippets'] = check_snippets(parsed[PLAN], args.bash, args.node)
    except (OSError, ValueError, KeyError, StopIteration, sqlite3.Error, subprocess.SubprocessError) as exc:
        errors.append(str(exc) or type(exc).__name__)
    report['errors'] = errors
    report['warnings'] = warnings
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
