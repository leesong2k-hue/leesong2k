"""온기 요리책: 검색·상세 페이지와 선택적으로 연결하는 AI 요리 도우미."""
from pathlib import Path
from html import escape
import base64
from uuid import uuid4
import streamlit as st
from cookbook import append_recipe, load_recipes, filter_recipes
from chat_ui import render_chat
from substitutions import load_substitutions, find_substitutions
from substitution_ui import show_table, render_table, render_ingredient_button, render_ingredient_choices, render_adapted_recipe

ROOT = Path(__file__).resolve().parent
RECIPE_PATH = ROOT / 'recipes.json'
CATEGORY_IMAGES = {'한식': 'korean-04.png', '중식': 'chinese-02.png',
                   '일식': 'japanese-04.png', '양식': 'western-01.png',
                   '디저트': 'dessert-category.png'}
st.set_page_config(page_title='자취피티 · 일상의 요리책', page_icon='🍲', layout='wide')
st.markdown(f"<style>{(ROOT / 'assets/style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
try:
    recipes = load_recipes(RECIPE_PATH)
except (OSError, ValueError, KeyError, TypeError) as error:
    st.error(f'레시피 데이터를 읽을 수 없습니다. recipes.json을 확인해 주세요. 상세: {error}')
    st.stop()
st.session_state.setdefault('category', '전체')
st.session_state.setdefault('recipe_id', None)
try:
    substitutions = load_substitutions(ROOT / 'substitutions.json')
except (OSError, ValueError, KeyError, TypeError) as error:
    substitutions = []
    st.error(f'대체표를 읽지 못했습니다. substitutions.json을 확인해 주세요. 상세: {error}')
FILTER_DEFAULTS = {'name': '', 'ingredients': '', 'time': '전체', 'difficulty': '전체'}
st.session_state.setdefault('filters', FILTER_DEFAULTS.copy())


def remember_filter(field):
    st.session_state.filters[field] = st.session_state['_filter_' + field]


def reset_filters():
    st.session_state.filters = FILTER_DEFAULTS.copy()
    for field, value in FILTER_DEFAULTS.items():
        st.session_state['_filter_' + field] = value

def open_recipe(recipe_id):
    st.session_state.substitution_table_open = False
    if recipe_id is not None:
        st.session_state.saved_category = st.session_state.category
    else:
        st.session_state.category = st.session_state.get('saved_category', '전체')
    st.session_state.recipe_id = recipe_id

def choose_category(category):
    st.session_state.substitution_table_open = False
    st.session_state.category = category
    st.session_state.recipe_id = None


def go_home():
    st.session_state.substitution_table_open = False
    st.session_state.category = '전체'
    st.session_state.recipe_id = None


is_home = st.session_state.category == '전체' and not st.session_state.recipe_id and not st.session_state.get('substitution_table_open')
hero_path = ROOT / 'assets/home-hero.png'
if is_home and hero_path.is_file():
    hero_image = base64.b64encode(hero_path.read_bytes()).decode('ascii')
    st.markdown(f'''<section class="welcome-hero" aria-label="다양한 요리가 차려진 자취피티 요리책 메인 배너"
        style="background-image:linear-gradient(90deg,rgba(27,32,23,.82),rgba(27,32,23,.30) 48%,rgba(27,32,23,.04)),url('data:image/png;base64,{hero_image}')">
        <div class="welcome-copy"><span class="welcome-eyebrow">자취요리+지피티</span>
        <h1>자취피티<span>재료는 가볍게, 식탁은 풍성하게.</span></h1>
        <p>가진 재료로 대화하고,<br>오늘의 메뉴를 찾아보세요.</p></div>
        </section>''', unsafe_allow_html=True)
else:
    st.markdown('<div class="brand">자취피티 <span>AI COOKING ASSISTANT</span></div>', unsafe_allow_html=True)
    st.caption('가진 재료로 대화하고, 분류를 따라 오늘의 메뉴를 찾아보세요.')
selected = next((r for r in recipes if r['id'] == st.session_state.recipe_id), None)
if not selected:
    st.session_state.recipe_id = None
if st.session_state.category not in {'전체', '한식', '일식', '중식', '양식', '디저트', *(r['category'] for r in recipes)}:
    st.session_state.category = '전체'
chat_column, cookbook_column = st.columns([0.9, 1.4], gap='large')
with chat_column:
    with st.container(border=True, key='cooking_chat_panel'):
        render_chat(ROOT, recipes, selected, substitutions)
with cookbook_column:
    nav = st.columns([1, 3])
    with nav[0]:
        st.button('⌂ 분류 선택', key='home', on_click=go_home, width='stretch')
    with nav[1]:
        st.caption('분류 선택' + (f"  ›  {st.session_state.category}" if st.session_state.category != '전체' else '') + (f"  ›  {selected['name']}" if selected else ''))
    st.button('소스 대체표 보기', key='open_substitution_table', on_click=show_table, width='stretch')
    if saved_name := st.session_state.pop('saved_recipe_notice', None):
        for key in ('new_recipe_name', 'new_recipe_ingredients', 'new_recipe_steps'):
            st.session_state.pop(key, None)
        st.success(f'{saved_name} 레시피를 저장했습니다.')
    with st.expander('새 레시피 등록'):
        with st.form('add_recipe'):
            recipe_name = st.text_input('요리 이름', key='new_recipe_name')
            recipe_category = st.selectbox('분류', list(dict.fromkeys(
                [*CATEGORY_IMAGES, *(r['category'] for r in recipes)])), key='new_recipe_category')
            ingredients_text = st.text_area('재료 (한 줄에 하나)', placeholder='계란 | 2개', key='new_recipe_ingredients')
            steps_text = st.text_area('조리 순서 (한 줄에 한 단계)', key='new_recipe_steps')
            if st.form_submit_button('레시피 저장'):
                ingredients = []
                for line in ingredients_text.splitlines():
                    if line.strip():
                        ingredient, _, quantity = line.partition('|')
                        ingredients.append({'name': ingredient.strip(), 'quantity_text': quantity.strip() or '분량 미기재'})
                recipe = {
                    'id': f'user-{uuid4().hex}', 'name': recipe_name.strip(),
                    'category': recipe_category, 'description': '사용자 등록 레시피',
                    'difficulty': '미기재', 'time_minutes': None, 'servings': None,
                    'ingredients': ingredients, 'steps': [line.strip() for line in steps_text.splitlines() if line.strip()],
                    'image': '', 'image_note': '사진 미등록', 'tip': '미기재', 'source': 'user',
                }
                try:
                    append_recipe(RECIPE_PATH, recipe)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    st.error(f'레시피를 저장하지 못했습니다. 요리 이름, 재료, 조리 순서를 확인해 주세요. 상세: {error}')
                else:
                    st.session_state.saved_recipe_notice = recipe['name']
                    choose_category(recipe['category'])
                    open_recipe(recipe['id'])
                    st.rerun()
    filters_active = st.session_state.filters != FILTER_DEFAULTS
    time_limits = {'전체': None, '15분 이내': 15, '30분 이내': 30, '1시간 이내': 60}
    if not selected and not st.session_state.get('substitution_table_open'):
        search_label = '전체 레시피 검색' if st.session_state.category == '전체' else '분류 내 레시피 검색'
        with st.expander(search_label, expanded=st.session_state.category == '전체'):
            for field, value in st.session_state.filters.items():
                st.session_state['_filter_' + field] = value
            a, b = st.columns(2)
            with a:
                st.text_input('요리 이름', placeholder='예: 볶음밥', key='_filter_name', on_change=remember_filter, args=('name',))
                st.selectbox('조리 시간', list(time_limits), key='_filter_time', on_change=remember_filter, args=('time',))
            with b:
                st.text_input('재료 이름', placeholder='예: 계란, 대파', key='_filter_ingredients', on_change=remember_filter, args=('ingredients',))
                st.selectbox('난이도', ['전체', *dict.fromkeys(r['difficulty'] for r in recipes)], key='_filter_difficulty', on_change=remember_filter, args=('difficulty',))
            st.button('검색 조건 초기화', key='reset_filters', on_click=reset_filters)
    if st.session_state.get('substitution_table_open'):
        render_table(substitutions)
    elif selected:
        st.button('← 메뉴 목록', key='back_to_menus', on_click=open_recipe, args=(None,))
        title_column, photo_column = st.columns([1, 1.6])
        with title_column:
            st.title(selected['name'])
            metadata = [selected['category']]
            if selected['time_minutes']:
                metadata.append(f"{selected['time_minutes']}분")
            if selected['servings']:
                metadata.append(f"기준 {selected['servings']}인분")
            st.caption(' · '.join(metadata))
            st.caption('사용자 제공 레시피 · 원문 분량 기준. 조리 안전은 별도로 확인하세요.')
        with photo_column:
            image_path = ROOT / selected['image']
            if image_path.is_file():
                st.image(str(image_path), width='stretch')
                st.caption(selected['image_note'])
        ingredients_column, steps_column = st.columns([1, 1.5], gap='medium')
        with ingredients_column:
            st.subheader('준비할 재료')
            portions = selected['servings']
            if portions:
                portions = st.number_input('만들 인분', min_value=1, max_value=20, value=selected['servings'], step=1, key='servings_' + selected['id'])
            else:
                st.caption('원문 분량 · 인분 미기재')
            section = None
            for index, item in enumerate(selected['ingredients']):
                if item.get('section') and item['section'] != section:
                    section = item['section']
                    st.markdown('**' + section + '**')
                quantity = item.get('quantity_text')
                if quantity is None:
                    quantity = f"{item['amount'] * portions / selected['servings']:.3g} {item['unit']}"
                if find_substitutions(item['name'], substitutions):
                    ingredient_label, ingredient_action = st.columns([1.2, 1])
                    with ingredient_label:
                        st.markdown(f"**{escape(item['name'])}**<br>{escape(quantity)}", unsafe_allow_html=True)
                    with ingredient_action:
                        render_ingredient_button(selected, index, item, substitutions)
                    render_ingredient_choices(selected, index, item, substitutions)
                else:
                    st.markdown(f"**{escape(item['name'])}**<br>{escape(quantity)}", unsafe_allow_html=True)
            st.caption('대체 재료는 괄호 안의 원문을 확인하세요. 약간·적당량은 임의 수치로 환산하지 않습니다.')
        with steps_column:
            st.subheader('조리 순서')
            steps = ''.join(f'<li>{escape(step)}</li>' for step in selected['steps'])
            st.markdown(f'<ol class="recipe-steps">{steps}</ol>', unsafe_allow_html=True)
            if selected.get('source') != 'user':
                st.info(selected['tip'])
        render_adapted_recipe(selected, substitutions)
    elif st.session_state.category == '전체' and not filters_active:
        st.header('어떤 요리가 당기세요?')
        st.caption('분류를 선택하면 메뉴 이름이 나타납니다.')
        icons = {'한식': '🍚', '중식': '🥟', '일식': '🍱', '양식': '🍝', '디저트': '🍰'}
        categories = list(dict.fromkeys([*icons, *(r['category'] for r in recipes)]))
        for start in range(0, len(categories), 3):
            for column, category in zip(st.columns(3), categories[start:start + 3]):
                with column:
                    with st.container(border=True, key='category_card_' + category):
                        category_image = ROOT / 'assets/recipes' / CATEGORY_IMAGES.get(category, '')
                        if category_image.is_file():
                            st.image(str(category_image), width='stretch')
                        st.button(f"{icons.get(category, '🍽️')}  {category}  →", key='category_' + category, on_click=choose_category, args=(category,), width='stretch')
                        st.caption(f"{sum(r['category'] == category for r in recipes)}가지 메뉴")
    else:
        category = st.session_state.category
        category_image = ROOT / 'assets/recipes' / CATEGORY_IMAGES.get(category, '')
        if category == '전체':
            st.header('전체 레시피 검색 결과')
        elif category_image.is_file():
            image_data = base64.b64encode(category_image.read_bytes()).decode('ascii')
            st.markdown(f'''<section class="cuisine-banner" style="background-image:linear-gradient(90deg,rgba(28,34,23,.82),rgba(28,34,23,.10)),url('data:image/png;base64,{image_data}')">
                <h2>{escape(category)} 메뉴</h2><p>오늘의 식탁을 채울 메뉴를 골라보세요.</p></section>''', unsafe_allow_html=True)
        else:
            st.header(category + ' 메뉴')
        st.caption('메뉴를 선택하면 재료와 조리 순서를 함께 볼 수 있습니다.')
        visible = filter_recipes(recipes, category=st.session_state.category,
                                 name=st.session_state.filters['name'], ingredients=st.session_state.filters['ingredients'],
                                 max_minutes=time_limits[st.session_state.filters['time']], difficulty=st.session_state.filters['difficulty'])
        if not visible:
            has_recipes = any(category in ('전체', r['category']) for r in recipes)
            st.info('검색 조건에 맞는 레시피가 없습니다. 검색어를 바꾸거나 필터를 줄여 보세요.' if has_recipes else '아직 등록된 레시피가 없습니다.')
        with st.container(key='menu_grid'):
            columns_count = max(2, (len(visible) + 3) // 4)
            for start in range(0, len(visible), columns_count):
                for column, recipe in zip(st.columns(columns_count, gap='small'), visible[start:start + columns_count]):
                    with column:
                        st.button(recipe['name'], key=recipe['id'], help=recipe['name'], on_click=open_recipe, args=(recipe['id'],), width='stretch')
        if visible:
            st.caption('등록된 레시피를 선택해 확인하세요.')
