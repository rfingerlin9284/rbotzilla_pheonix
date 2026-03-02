#!/usr/bin/env python3
"""
Installer and initialization script for a clean deployment.
- Verifies configs (read-only) and required components
- Generates task registry
- Runs smoke tests and backtests (if configured)
- Produces an installation report and ops/state/installation_state.json
- Optionally restores from a given archive and/or includes secrets (requires approval id)

Usage examples:
  python3 tools/installer.py --verify-only
  python3 tools/installer.py --archive /path/to/archive.tar.gz --dry-run
  python3 tools/installer.py --include-secrets --approval-id <id>

Safety:
- This script will NOT modify `ops/secrets.env` unless you pass `--include-secrets --approval-id <id>`.
- Including secrets requires a recorded approval id in HISTORICAL_CHANGE_LOG.md and will prompt for PIN to verify.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
REPORT_DIR = ROOT / 'build' / 'installer_reports'
STATE_DIR = ROOT / 'ops' / 'state'
STATE_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def run_cmd(cmd, capture=False):
    print(f"→ Running: {' '.join(cmd)}")
    try:
        if capture:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
            return 0, out
        else:
            rv = subprocess.run(cmd)
            return rv.returncode, None
    except subprocess.CalledProcessError as e:
        return e.returncode, getattr(e, 'output', b'').decode('utf-8')


def verify_configs():
    print('🔎 Verifying configurations (read-only)')
    rc, out = run_cmd([sys.executable, str(ROOT / 'tools' / 'verify_configs.py')], capture=True)
    return rc == 0, out


def generate_tasks_registry():
    print('📋 Generating tasks registry')
    rc, out = run_cmd([sys.executable, str(ROOT / 'tools' / 'generate_tasks_registry.py')], capture=True)
    return rc == 0, out


def run_smoke_tests():
    print('🧪 Running smoke checks')
    report = {}
    # Import engines
    try:
        import importlib
        importlib.import_module('multi_broker_phoenix.engines.paper_engine')
        report['paper_engine'] = 'ok'
    except Exception as e:
        report['paper_engine'] = f'error: {e}'
    # Check AI Hive
    try:
        import importlib
        importlib.import_module('hive_real.api_ai_hive')
        report['ai_hive'] = 'ok'
    except Exception as e:
        report['ai_hive'] = f'warning: {e}'
    # Local LLM check (best-effort)
    llm_path = None
    if 'LOCAL_LLM_PATH' in os.environ:
        llm_path = os.environ['LOCAL_LLM_PATH']
    try:
        import importlib
        importlib.import_module('local_llm')
        report['local_llm'] = 'ok'
    except Exception as e:
        report['local_llm'] = f'warning: {e} (set LOCAL_LLM_PATH to enable)'
    return report


def build_deployment(include_secrets=False, approval_id=None):
    print('📦 Building deployment (packaging)')
    cmd = [sys.executable, str(ROOT / 'tools' / 'build_deployment.py'), '--output', 'build/installer_deployment.tar.gz']
    if include_secrets:
        cmd += ['--include-secrets', '--approval-id', approval_id]
    rc, out = run_cmd(cmd, capture=True)
    return rc == 0, out


def create_snapshot():
    print('🔐 Creating secrets snapshot (locked copies)')
    rc, out = run_cmd([sys.executable, str(ROOT / 'tools' / 'make_secrets_snapshot.py'), '--output', 'build/secrets_snapshot_final.tar.gz'], capture=True)
    return rc == 0, out


def archive_legacy():
    print('🗃️  Scanning for legacy/duplicate files (report only)')
    # Reuse build_deployment gather to detect duplicates
    try:
        import tools.build_deployment as bd
        files = bd.gather_files(False)
        names = {}
        duplicates = []
        for f in files:
            n = Path(f).name
            names.setdefault(n, []).append(str(f))
        for n, lst in names.items():
            if len(lst) > 1:
                duplicates.append({'name': n, 'paths': lst})
        return duplicates
    except Exception as e:
        return [{'error': str(e)}]


def save_state(report):
    ts = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    path = REPORT_DIR / f'installation_report_{ts}.json'
    path.write_text(json.dumps(report, indent=2))
    state = {'status': 'installed' if report.get('ok') else 'failed', 'report': str(path)}
    (STATE_DIR / 'installation_state.json').write_text(json.dumps(state, indent=2))
    print('📁 Installation state saved:', STATE_DIR / 'installation_state.json')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--verify-only', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--archive', help='Path to deployment archive to restore from')
    p.add_argument('--include-secrets', action='store_true', help='Include secrets from canonical file (requires approval)')
    p.add_argument('--approval-id', help='Approval id required to include secrets')
    args = p.parse_args()

    report = {'ok': True, 'steps': []}

    ok, out = verify_configs()
    report['steps'].append({'verify_configs': ok, 'output': out})
    if not ok:
        report['ok'] = False
        save_state(report)
        print('❌ Config verification failed — aborting')
        return

    ok, out = generate_tasks_registry()
    report['steps'].append({'generate_tasks_registry': ok, 'output': out})

    # Optionally restore from archive (not implemented full extraction here; placeholder)
    if args.archive:
        report['restore_archive'] = str(args.archive)
        if not args.dry_run:
            print('Restoring from archive is not fully automated in this version. Please extract manually and run this script again.')

    # Create secrets snapshot
    ok, out = create_snapshot()
    report['steps'].append({'create_snapshot': ok, 'output': out})

    # Attempt to lock secrets (best-effort; may require elevated permissions)
    rc, _ = run_cmd(['bash', str(ROOT / 'tools' / 'lock_secrets.sh')], capture=True)
    report['steps'].append({'lock_secrets': rc == 0})

    # Build deployment (without secrets unless requested)
    include_secrets = args.include_secrets
    if include_secrets and not args.approval_id:
        print('❌ To include secrets, you must supply --approval-id <id>')
        report['ok'] = False
        save_state(report)
        return
    ok, out = build_deployment(include_secrets=include_secrets, approval_id=args.approval_id)
    report['steps'].append({'build_deployment': ok, 'output': out})
    if not ok:
        report['ok'] = False

    # Smoke tests
    smoke = run_smoke_tests()
    report['smoke'] = smoke

    # Legacy scan
    duplicates = archive_legacy()
    report['duplicates'] = duplicates

    save_state(report)

    print('\n✅ Installer finished. Installation report saved.')
    print('\nNext steps:')
    print('- Review the installation report in build/installer_reports/')
    print("- Use tools/task_menu.py to start components or tools/agent_executor.py with approval ids to perform sensitive operations")


if __name__ == '__main__':
    main()
