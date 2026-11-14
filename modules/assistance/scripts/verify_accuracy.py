"""Measure authorized disposable audio without logging media, reference or transcript."""

import sys as _sys
from pathlib import Path as _Path
_repository = _Path(__file__).resolve().parents[3]
_sys.path.insert(0, str(_repository))
_sys.path.insert(0, str(_repository / "modules"))
import argparse
import json
from pathlib import Path
import re
import sys
import time
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from assistance.transcription import LocalTranscription, SpeechError
from shared.assistance_settings import read_ai_document
from shared.paths import ASSISTANCE_ROOT


def words(text):
    return re.findall(r'\w+', unicodedata.normalize('NFKC', text).casefold())


def word_errors(reference, actual):
    expected, observed = words(reference), words(actual)
    previous = list(range(len(observed) + 1))
    for index, word in enumerate(expected, 1):
        current = [index]
        for offset, other in enumerate(observed, 1):
            current.append(min(current[-1] + 1, previous[offset] + 1, previous[offset-1] + (word != other)))
        previous = current
    return {'reference_words': len(expected), 'recognized_words': len(observed),
        'word_errors': previous[-1], 'word_error_rate': round(previous[-1] / max(1, len(expected)), 4)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio', type=Path)
    parser.add_argument('--reference', type=Path, help='Authorized reference text, never printed')
    parser.add_argument('--model', help='Explicit comparison only; never an automatic fallback')
    parser.add_argument('--language', help='auto or an explicitly allowed language')
    parser.add_argument('--beam-size', type=int)
    parser.add_argument('--compute-type')
    parser.add_argument('--cpu-threads', type=int)
    parser.add_argument('--expected-title', action='append', default=[])
    args = parser.parse_args()
    config = read_ai_document(ASSISTANCE_ROOT / 'config.json')
    for key in ('model', 'language', 'beam_size', 'compute_type', 'cpu_threads'):
        value = getattr(args, key)
        if value is not None:
            config['transcription'][key] = value
    config['transcription']['local_files_only'] = True
    service = LocalTranscription(config)
    import av
    import ctranslate2
    with av.open(str(args.audio)) as container:
        stream = container.streams.audio[0]
        metadata = {'codec': stream.codec_context.name, 'sample_rate': stream.codec_context.sample_rate,
            'channels': stream.codec_context.channels, 'decoded_input_samples': sum(frame.samples for frame in container.decode(stream))}
    data = args.audio.read_bytes()
    report = {'settings': {key: service.settings[key] for key in ('model', 'device', 'compute_type', 'language',
        'beam_size', 'cpu_threads', 'segment_seconds', 'condition_on_previous_text', 'vad_filter')},
        'audio': metadata, 'input_bytes': len(data), 'supported_cpu_precisions': sorted(ctranslate2.get_supported_compute_types('cpu'))}
    start = time.monotonic()
    try:
        model = service.model()
        report['load_seconds'] = round(time.monotonic() - start, 3)
        report['effective_compute_type'] = str(model.model.compute_type)
        report['multilingual'] = bool(model.model.is_multilingual)
        started = time.monotonic()
        cpu_started = time.process_time()
        result = service.transcribe(data)
        report.update(processing_seconds=round(time.monotonic() - started, 3), cpu_seconds=round(time.process_time() - cpu_started, 3),
            duration_seconds=result['duration_seconds'], detected_language=result['language'], complete=result['complete'])
        if args.reference:
            report.update(word_errors(args.reference.read_text(encoding='utf-8'), result['text']))
        if args.expected_title:
            normalized = ' '.join(words(result['text']))
            report['expected_titles'] = len(args.expected_title)
            report['matched_titles'] = sum(' '.join(words(title)) in normalized for title in args.expected_title)
        try:
            import resource
            report['peak_rss_mib'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        except ImportError:
            pass
        print(json.dumps(report))
        return 0
    except SpeechError as error:
        print(json.dumps({'failure': error.diagnostic(), 'settings': report['settings']}))
        return 1
    finally:
        service.close()


if __name__ == '__main__':
    raise SystemExit(main())
