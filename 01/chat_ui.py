"""요리책 화면과 독립적인 세션 채팅 UI."""
import streamlit as st
from ai_assistant import CookingAIError, ask_ai, settings, redact
from cookbook import chat_recipe_choices
from substitutions import substitution_chat_answer


def clear_chat():
    st.session_state.cooking_messages = []
    st.session_state.pop('cooking_chat_error', None)


def open_chat_recipe(recipe_id, category):
    st.session_state.substitution_table_open = False
    st.session_state.category = category
    st.session_state.saved_category = category
    st.session_state.recipe_id = recipe_id


def render_chat(root, recipes, selected, substitutions=None):
    st.header('🌿 AI 요리 도우미')
    st.caption('냉장고에 있는 재료를 알려주세요.')
    config = settings(root)
    gemini = config['AI_BACKEND'] == 'gemini'
    token = config['GEMINI_API_KEY'] if gemini else config['HF_TOKEN']
    provider = 'Google Gemini' if gemini else 'Hugging Face와 추론 제공자'
    with st.expander('AI 이용 안내'):
        st.caption('AI 답변과 사용자 제공 레시피의 안전성은 미검증입니다. 알레르기 및 조리 안전을 보장하지 않습니다.')
        st.caption(f'질문·최근 대화 12회·저장 레시피 및 현재 화면 정보가 {provider}에 전달됩니다. 개인정보나 API 키는 입력하지 마세요.')
        if gemini:
            st.caption('무료 프로젝트의 API 키를 사용하세요. 무료 한도 초과 시 오류를 안내합니다. 무료 서비스 입력은 Google 제품 개선에 사용될 수 있습니다.')
    st.session_state.setdefault('cooking_messages', [])
    portions = st.session_state.get('servings_' + selected['id'], selected['servings']) if selected else None
    context = selected['name'] if selected else '전체 요리책'
    if portions:
        context += f' · {portions}인분'
    st.caption(f'현재 문맥: {context}')
    if not token:
        st.info('저장 메뉴 검색은 바로 사용할 수 있습니다. AI 조리 상담은 .env에 GEMINI_API_KEY를 설정해 주세요.' if gemini else '저장 메뉴 검색은 바로 사용할 수 있습니다. AI 조리 상담은 .env에 HF_TOKEN을 설정해 주세요.')
        if gemini:
            st.markdown('[Google AI Studio에서 API 키 발급](https://aistudio.google.com/apikey) · [사용량·한도 확인](https://aistudio.google.com/usage)')
    with st.container(height=320, border=False):
        if not st.session_state.cooking_messages:
            with st.container(key='cooking_chat_examples'):
                st.info('예: 계란, 대파, 두부가 있어. 무엇을 만들까?\n\n'
                        '예: 계란,대파로 만들 수 있는 중식메뉴를 추천해줘\n\n'
                        '예: 사과식초를 뭐로 대체할 수 있을까?')
        for index, message in enumerate(st.session_state.cooking_messages):
            with st.chat_message(message['role'], avatar='🧑‍🍳' if message['role'] == 'assistant' else '🙂'):
                if 'recipe_ids' in message:
                    matches = [r for recipe_id in message['recipe_ids'] for r in recipes if r['id'] == recipe_id]
                    if matches:
                        for recipe in matches:
                            with st.container(key=f"chat_recipe_row_{index}_{recipe['id']}", horizontal=True,
                                              vertical_alignment='center', gap='small'):
                                st.markdown(f"추천 메뉴는 {recipe['name']}입니다.", width='content')
                                st.button('보기', key=f"chat_recipe_{index}_{recipe['id']}",
                                          help=f"{recipe['name']} 레시피 열기", on_click=open_chat_recipe,
                                          args=(recipe['id'], recipe['category']), width='content')
                    else:
                        st.info('등록된 메뉴 중 일치하는 요리가 없습니다. 다른 재료로 검색해 주세요.')
                else:
                    st.markdown(redact(message['content'], token))
    if st.session_state.cooking_messages:
        st.button('대화 지우기', key='clear_cooking_chat', on_click=clear_chat)
    if prompt := st.chat_input('예: 대파, 계란을 소비할 수 있는 메뉴를 추천해 줘', max_chars=3000):
        prompt = redact(prompt, token)
        substitution_answer = substitution_chat_answer(prompt, substitutions or [])
        if substitution_answer is not None:
            st.session_state.cooking_messages.extend([
                {'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': substitution_answer}])
            st.session_state.pop('cooking_chat_error', None)
            st.rerun()
        choices = chat_recipe_choices(prompt, recipes)
        if choices is not None:
            content = '선택 가능한 저장 메뉴: ' + ', '.join(r['name'] for r in choices) if choices else '등록된 메뉴 중 일치하는 요리가 없습니다.'
            st.session_state.cooking_messages.extend([
                {'role': 'user', 'content': prompt},
                {'role': 'assistant', 'content': content, 'recipe_ids': [r['id'] for r in choices]}])
            st.session_state.pop('cooking_chat_error', None)
            st.rerun()
        try:
            with st.spinner('요리책을 참고해 답변을 만들고 있습니다…'):
                answer = ask_ai(config, st.session_state.cooking_messages, prompt, recipes, selected, portions)
            st.session_state.cooking_messages.extend([{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': answer}])
            st.session_state.pop('cooking_chat_error', None)
            st.rerun()
        except CookingAIError as error:
            st.session_state.cooking_chat_error = str(error)
    if st.session_state.get('cooking_chat_error'):
        st.error(st.session_state.cooking_chat_error)
        if gemini:
            st.markdown('[Google AI Studio API 키·프로젝트 확인](https://aistudio.google.com/apikey) · [사용량·한도 확인](https://aistudio.google.com/usage)')
        elif '(402)' in st.session_state.cooking_chat_error:
            st.markdown('[Hugging Face 결제·크레딧 설정](https://huggingface.co/settings/billing) · '
                        '[추론 제공자·사용량 확인](https://huggingface.co/settings/inference-providers)')
            st.caption('토큰을 만든 계정으로 로그인하세요. 크레딧 추가는 유료이며, 앱에서 결제를 자동 진행하지 않습니다. 처리 후 같은 질문을 다시 입력하면 됩니다.')
