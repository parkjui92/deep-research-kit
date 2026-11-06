"""Transitions found by exercising the review desk, not just first-time saves."""
from streamlit.testing.v1 import AppTest
from test_ui import _project_with_value, _workbench_script

from deep_research import integrity
from deep_research import workflow as w
from deep_research.project import read_json


def review_app(project):
    app = AppTest.from_function(_workbench_script, args=(str(project.root),), default_timeout=15)
    app.session_state['drk_claude_ready'] = False
    app.session_state['cc_status'] = {'available': False, 'reason': 'test'}
    return app


def test_latest_integrity_is_shown_in_both_review_layouts(tmp_path):
    p, run = _project_with_value(tmp_path, 'Original finding')
    sid = p.catalog()[0]['id']
    flag = integrity.from_search({'doi': '10.1/retracted', 'retracted': True})
    p.set_integrity(sid, flag)  # notice checked after the run was frozen
    app = review_app(p).run()
    assert not app.exception
    assert any('철회됨' in e.value for e in app.error)
    app.button(key='wb_focus').click().run()
    assert not app.exception
    assert any('철회됨' in e.value for e in app.error)
    assert not w.manifest(p, run)['sources'][0].get('integrity')


def test_edited_value_can_be_restored_to_original_without_losing_history(tmp_path):
    p, run = _project_with_value(tmp_path, 'Original finding')
    row = w.evidence(p, run)[0]
    w.review(p, run, row['id'], 'edit', 'Corrected after reading', 'Tester', 'Corrected finding')
    app = review_app(p)
    app.session_state['wb_pick'] = row['id']
    app.session_state['wb_layout'] = '집중 검토'
    app.run()
    app.radio(key='wb_decision_' + row['id']).set_value('accept').run()
    assert not any(t.label.startswith('수정한 값') for t in app.text_area)
    assert any('원래 값으로 채택' in e.value for e in app.info)
    next(e for e in app.text_input if e.label.startswith('검토자')).set_value('Tester')
    next(e for e in app.checkbox if e.label.startswith('원문의 앞뒤')).check()
    next(e for e in app.button if e.label == '저장하고 다음 미검토로').click().run()
    assert not app.exception and not app.error
    saved = next(r for r in w.evidence(p, run) if r['id'] == row['id'])
    assert saved['review']['status'] == 'accept'
    assert w.reviewed_value(saved) == 'Original finding'
    history = read_json(p.run_dir(run) / 'reviews.json')
    assert history[-1]['previous']['edited_value'] == 'Corrected finding'


def test_last_pending_review_shows_completion_and_report_route(tmp_path):
    p, run = _project_with_value(tmp_path, 'Original finding')
    rows = w.evidence(p, run)
    for row in rows[:-1]:
        w.review(p, run, row['id'], 'reject', 'Not applicable', 'Tester')
    app = review_app(p).run()
    app.selectbox(key='wb_filter').set_value('미검토').run()
    app.button(key='wb_focus').click().run()
    app.radio(key='wb_decision_' + rows[-1]['id']).set_value('accept').run()
    next(t for t in app.text_input if t.label.startswith('이유')).set_value('PDF checked')
    next(t for t in app.text_input if t.label.startswith('검토자')).set_value('Tester')
    next(c for c in app.checkbox if c.label.startswith('원문의 앞뒤')).check()
    next(b for b in app.button if b.label == '저장하고 다음 미검토로').click().run()
    assert not app.exception
    assert any('미검토 근거를 모두 처리' in e.value for e in app.success)
    app.button(key='wb_queue_report').click().run()
    assert not app.exception
    assert app.session_state['wb_view'] == '보고서에 쓰기'


def test_web_ai_extraction_is_available_even_when_claude_is_installed(tmp_path, monkeypatch):
    from deep_research import providers
    p, _ = _project_with_value(tmp_path, 'Original finding')
    monkeypatch.setattr(providers, 'claude_code_status', lambda: {'available': True, 'reason': ''})
    monkeypatch.setattr(providers, 'run_claude_code', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('must not run')))
    app = review_app(p)
    app.session_state['cc_status'] = {'available': True, 'reason': ''}
    app.run()
    previous = set(p.runs())
    app.button(key='wb_make_request').click().run()
    assert not app.exception
    assert len(set(p.runs()) - previous) == 1
    assert any(t.label == 'AI 응답(JSON) 붙여넣기' for t in app.text_area)


def test_saving_middle_item_visits_next_pending_before_wrapping(tmp_path):
    p, run = _project_with_value(tmp_path, 'Original finding')
    rows = w.evidence(p, run)
    app = review_app(p).run()
    app.button(key='cell-' + rows[2]['id']).click().run()
    app.radio(key='wb_decision_' + rows[2]['id']).set_value('hold').run()
    next(t for t in app.text_input if t.label.startswith('이유')).set_value('Needs context')
    next(t for t in app.text_input if t.label.startswith('검토자')).set_value('Tester')
    next(b for b in app.button if b.label == '저장하고 다음 미검토로').click().run()
    assert not app.exception
    assert app.session_state['wb_pick'] == rows[3]['id']
    app.radio(key='wb_decision_' + rows[3]['id']).set_value('reject').run()
    next(t for t in app.text_input if t.label.startswith('이유')).set_value('Not relevant')
    next(b for b in app.button if b.label == '저장하고 다음 미검토로').click().run()
    assert not app.exception
    assert app.session_state['wb_pick'] == rows[0]['id']
