"""Refresh the shared Unicode 16 UAX #29 conformance fixture, without application data."""
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://www.unicode.org/Public/16.0.0/ucd/auxiliary/GraphemeBreakTest.txt'


def main():
    with urlopen(SOURCE, timeout=30) as response:
        lines = response.read().decode('utf-8').splitlines()
    cases = []
    for line in lines:
        tokens = line.split('#', 1)[0].split()
        if not tokens:
            continue
        segments, current = [], ''
        for token in tokens:
            if token == '÷':
                if current:
                    segments.append(current)
                    current = ''
            elif token != '×':
                current += chr(int(token, 16))
        cases.append({'text': ''.join(segments), 'segments': segments})
    target = ROOT / 'qa/grapheme-vectors.json'
    target.write_text(json.dumps({'unicode_version': '16.0.0', 'source': SOURCE,
        'license': 'https://www.unicode.org/license.txt', 'cases': cases}, ensure_ascii=True, indent=2)+'\n', encoding='utf-8')
    with urlopen('https://www.unicode.org/license.txt', timeout=30) as response:
        (ROOT/'qa/UNICODE_LICENSE.txt').write_bytes(response.read())
    print(f'Wrote {len(cases)} shared Unicode conformance cases')


if __name__ == '__main__':
    main()
