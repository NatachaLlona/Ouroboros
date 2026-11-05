"""Inspect the active speech runtime without media, credentials or exception-body logging."""
import sys
from pathlib import Path
_REPOSITORY_ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(_REPOSITORY_ROOT),str(_REPOSITORY_ROOT/"scripts")]
import argparse
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.assistance_settings import read_ai_document
from shared.paths import ASSISTANCE_ROOT
from assistance.transcription import LocalTranscription, SpeechError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--load-model', action='store_true', help='Load the configured model; may download unless offline is selected.')
    parser.add_argument('--offline', action='store_true', help='Never download model files during the load probe.')
    arguments = parser.parse_args()
    print('Interpreter:', sys.executable)
    print('Python:', sys.version.split()[0])
    config = read_ai_document(ASSISTANCE_ROOT/'config.json')
    service = LocalTranscription(config)
    public_keys = ('model', 'device', 'compute_type', 'cache_directory', 'local_files_only',
                   'idiomas_transcricao', 'max_audio_bytes', 'max_duration_seconds', 'max_concurrency', 'cpu_threads',
                   'upload_timeout_seconds', 'processing_timeout_seconds', 'request_timeout_seconds', 'max_transcript_chars', 'segment_seconds')
    print('Speech settings:', json.dumps({key: service.settings[key] for key in public_keys}))
    failed = False
    for module, package in (('av', 'av'), ('numpy', 'numpy'), ('faster_whisper', 'faster-whisper'), ('ctranslate2', 'ctranslate2'), ('onnxruntime', 'onnxruntime')):
        try:
            importlib.import_module(module)
            print('Dependency:', package, importlib.metadata.version(package), 'imported')
        except Exception as error:
            failed = True
            print('Dependency:', package, type(error).__name__, 'missing_module='+str(getattr(error, 'name', None)))
    cache = service.cache_path
    print('Cache:', cache, 'exists='+str(cache.is_dir()))
    print('Cached model configurations:', len(list(cache.glob('**/config.json'))))
    parent = cache
    while not parent.exists():
        parent = parent.parent
    try:
        with tempfile.TemporaryFile(dir=parent) as probe:
            probe.write(b'speech-cache-permission-probe')
        print('Nearest existing cache ancestor:', parent, 'write_probe=passed')
    except OSError as error:
        failed = True
        print('Cache write probe:', type(error).__name__)
    if arguments.load_model:
        if arguments.offline:
            service.settings = {**service.settings, 'local_files_only': True}
        try:
            service.model()
            print('Model loaded; no audio was recorded or transcribed.')
        except SpeechError as error:
            failed = True
            print('Model failure:', json.dumps(error.diagnostic()))
        finally:
            service.close()
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
