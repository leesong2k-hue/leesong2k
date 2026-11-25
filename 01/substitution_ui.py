"""대체표와 세션에서만 유지하는 대체 레시피 UI."""
import streamlit as st
from substitutions import find_substitutions, option_combinations, normalize

CATEGORY_LABELS = {'한식': '한식', '일본식': '일식', '중식': '중식', '서양식': '서양', '동남아식': '동남아'}


def clear_table_search():
    st.session_state.substitution_search = ''


def show_table():
    st.session_state.substitution_table_open = True


def close_table():
    st.session_state.substitution_table_open = False


def render_table(entries):
    st.header('소스 대체표')
    st.caption('모든 조합은 실제 조리 미검증 후보입니다. 동일한 맛·비율을 보장하지 않습니다.')
    counts = {category: sum(category in e.get('categories', [e['category']]) for e in entries) for category in CATEGORY_LABELS}
    category = st.radio('소스 분류', ['전체', *CATEGORY_LABELS],
                        format_func=lambda key: '전체' if key == '전체' else CATEGORY_LABELS[key] + f" ({counts[key]})",
                        horizontal=True, key='substitution_category', on_change=clear_table_search)
    query = st.text_input('소스·대체 재료·사용 용도 검색', key='substitution_search')
    st.button('검색어 지우기', key='clear_substitution_search', on_click=clear_table_search)
    rows = []
    for e in entries:
        categories = e.get('categories', [e['category']])
        labels = [CATEGORY_LABELS.get(c, c) for c in categories]
        if category != '전체' and category not in categories:
            continue
        searchable = ' '.join([e['original'], e['substitutes_text'], *e['usage'], *e.get('aliases', []), *categories, *labels])
        if query.strip() and normalize(query) not in normalize(searchable):
            continue
        rows.append({'분류': ' · '.join(labels), '원래 소스': e['original'], '대체 재료': e['substitutes_text'], '사용 용도': ', '.join(e['usage'])})
    st.caption(f"전체 {len(entries)}개 대체 조합 중 {len(rows)}개 표시 · 여러 분류의 공통 조합은 각 분류에서 조회됩니다.")
    if rows:
        st.dataframe(rows, hide_index=True, width='stretch', height=420)
    else:
        st.info('검색 조건에 맞는 대체 정보가 없습니다.')
    st.button('← 요리책으로 돌아가기', key='close_substitution_table', on_click=close_table)


def apply_substitution(recipe_id, ingredient_index, entry_id, combination):
    st.session_state.setdefault('recipe_substitutions', {}).setdefault(recipe_id, {})[ingredient_index] = {
        'entry_id': entry_id, 'combination': combination}


def remove_substitution(recipe_id, ingredient_index):
    st.session_state.get('recipe_substitutions', {}).get(recipe_id, {}).pop(ingredient_index, None)


def render_ingredient_button(recipe, index, item, entries):
    candidates = find_substitutions(item['name'], entries)
    if not candidates:
        return
    rid = recipe['id']
    prefix = f'sub_{rid}_{index}'
    if st.button('대체 재료 보기', key=prefix, width='stretch'):
        current = st.session_state.get('substitution_detail')
        st.session_state.substitution_detail = None if current == (rid, index) else (rid, index)


def render_ingredient_choices(recipe, index, item, entries):
    candidates = find_substitutions(item['name'], entries)
    rid = recipe['id']
    prefix = f'sub_{rid}_{index}'
    if st.session_state.get('substitution_detail') != (rid, index):
        return
    for candidate in candidates:
        with st.container(border=True):
            st.markdown('**대체 재료: ' + candidate['substitutes_text'] + '**')
            st.write('원래 재료와의 차이: ' + candidate['taste_difference'])
            st.write('분량: ' + candidate['adjustment'])
            for example in candidate.get('trial_examples', []):
                st.caption('분량 예시 · 미검증: ' + example['formula'])
            st.write('사용 용도: ' + ', '.join(candidate['usage']))
            options = option_combinations(candidate)
            combination = st.selectbox('적용할 조합', options, key=f"{prefix}_option_{candidate['id']}") if len(options) > 1 else options[0]
            st.button('이 조합 적용', key=f"{prefix}_apply_{candidate['id']}", on_click=apply_substitution,
                      args=(rid, index, candidate['id'], combination))


def render_adapted_recipe(recipe, entries):
    selections = st.session_state.get('recipe_substitutions', {}).get(recipe['id'], {})
    valid = {index: choice for index, choice in selections.items()
             if index < len(recipe['ingredients']) and any(e['id'] == choice['entry_id'] for e in entries)}
    if not valid:
        return
    st.subheader('선택한 대체 레시피 · ' + recipe['name'])
    st.warning('선택한 재료만 변경한 별도 버전입니다. 배합량과 조리 순서의 적합성은 미검증입니다. 원본 분량을 그대로 치환하지 마세요.')
    rows = []
    for index, item in enumerate(recipe['ingredients']):
        choice = valid.get(index)
        rows.append({'원래 재료': item.get('original_text', item['name']),
                     '대체 버전': choice['combination'] + ' · 분량 미검증, 소량씩 조절' if choice else item.get('original_text', item['name'])})
    st.dataframe(rows, hide_index=True, width='stretch')
    for index in valid:
        st.button(recipe['ingredients'][index]['name'] + ' 대체 취소', key=f"undo_sub_{recipe['id']}_{index}",
                  on_click=remove_substitution, args=(recipe['id'], index))
    st.caption('조리 순서는 위의 원문을 참고하세요. 선택한 재료에 따른 가열·농도 조정은 별도 확인이 필요합니다.')
