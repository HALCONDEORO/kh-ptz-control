"""Safety limits for the metadata-only PR labeling workflow."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow():
    return yaml.safe_load((ROOT / '.github/workflows/pr-labeler.yml').read_text())


def test_metadata_events_only_with_no_checkout_or_shell_execution():
    data = workflow()
    events = data.get('on', data.get(True))  # PyYAML YAML 1.1 parses on as True.
    assert events == {'workflow_run': {'workflows': ['CI'], 'types': ['completed']}}
    job = data['jobs']['label']
    assert ' '.join(job['if'].split()) == (
        "github.event.workflow_run.event == 'pull_request' && "
        'github.event.workflow_run.pull_requests[0].number > 0 && '
        'github.event.workflow_run.pull_requests[1] == null && '
        'github.event.workflow_run.pull_requests[0].base.repo.id == github.repository_id'
    )
    assert set(data['jobs']) == {'label'}
    assert set(job) == {'if', 'runs-on', 'timeout-minutes', 'permissions', 'steps'}
    assert job['runs-on'] == 'ubuntu-latest'
    assert job['timeout-minutes'] == 2
    assert len(job['steps']) == 1
    step = job['steps'][0]
    assert 'run' not in step
    assert step['uses'] == 'actions/labeler@b8dd2d9be0f68b860e7dae5dae7d772984eacd6d'
    assert set(step) == {'name', 'uses', 'with'}
    assert step['with'] == {
        'pr-number': '${{ github.event.workflow_run.pull_requests[0].number }}',
        'sync-labels': False,
        'configuration-path': '.github/labeler.yml',
    }


def test_only_required_token_permissions_and_no_new_secret():
    data = workflow()
    assert data['permissions'] == {'contents': 'read'}
    assert data['jobs']['label']['permissions'] == {'contents': 'read', 'pull-requests': 'write'}
    assert 'secrets.' not in str(data)
    assert data['concurrency'] == {
        'group': 'pr-labeler-${{ github.event.workflow_run.pull_requests[0].number || github.run_id }}',
        'cancel-in-progress': True,
    }


def test_label_config_uses_existing_documentation_label_only():
    data = yaml.safe_load((ROOT / '.github/labeler.yml').read_text())
    assert data == {'documentation': [{'changed-files': [{'any-glob-to-any-file': ['**/*.md', 'docs/**']}]}]}
