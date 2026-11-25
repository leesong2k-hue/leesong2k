"""화면과 독립적인 레시피 데이터 로더."""
import json
import os
import re
from tempfile import NamedTemporaryFile
import unicodedata

from filelock import FileLock

_ingredient_aliases = {'참치캔': '참치', '달걀': '계란', '사각어묵': '어묵'}
_category_pattern = re.compile(
    r'(?<!\w)(한식|일식|중식|양식|디저트)'
    r'(?=$|\W|메뉴|요리|음식|레시피|추천|만|으로|로|에서|중|의|은|는|이|가|을|를|나|과|와)'
)


def _normalize(text):
    return ''.join(unicodedata.normalize('NFKC', text).casefold().split())


def _matches_ingredient(term, name):
    return term in name or _ingredient_aliases.get(term, term) == _ingredient_aliases.get(name, name)


def filter_recipes(recipes, name='', ingredients='', category='전체', max_minutes=None, difficulty='전체'):
    """부분 일치 검색. 쉼표로 나눈 재료와 모든 필터를 AND로 결합합니다."""
    name = _normalize(name)
    terms = [_normalize(term) for term in re.split('[,，]', ingredients) if _normalize(term)]
    return [recipe for recipe in recipes
            if name in _normalize(recipe['name'])
            and all(any(_matches_ingredient(term, _normalize(item['name'])) for item in recipe['ingredients']) for term in terms)
            and (category == '전체' or recipe['category'] == category)
            and (max_minutes is None or (recipe['time_minutes'] is not None and recipe['time_minutes'] <= max_minutes))
            and (difficulty == '전체' or recipe['difficulty'] == difficulty)]


def chat_recipe_choices(prompt, recipes):
    """메뉴 탐색은 저장 데이터로 처리하고 조리 질문은 기존 AI로 전달합니다."""
    text = _normalize(prompt)
    if any(word in text for word in ('대신', '대체', '알레르기', '조리법', '조리순서', '어떻게', '왜', '몇분', '몇인분')):
        return None
    categories = set(_category_pattern.findall(unicodedata.normalize('NFKC', prompt)))
    consumption_request = re.search(r'(?:을|를)?(?:소비|소진|활용)(?:할|하는)', text)
    ingredient_query = text[:consumption_request.start()] if consumption_request else text
    # 질문에 쓰인 '무엇'이 재료 '무'로 잡히지 않도록 합니다.
    ingredient_query = ingredient_query.replace('무엇', '?')
    named_recipes = [r for r in recipes if _normalize(r['name']) in ingredient_query]
    if named_recipes:
        return [r for r in named_recipes if not categories or r['category'] in categories]
    ingredient_names = [
        {_normalize(i['name']) for i in r['ingredients']
         if consumption_request or i.get('section', '재료') == '재료'}
        for r in recipes
    ]
    terms = sorted(set().union(*ingredient_names), key=len, reverse=True)
    # '참치캔'은 '참치'로도 찾을 수 있게 합니다.
    found = []
    for term in terms:
        alias = _ingredient_aliases.get(term, term)
        if term in ingredient_query or alias in ingredient_query:
            if not any(term in existing for existing in found):
                found.append(term)
    recommendation = consumption_request or any(
        word in text for word in ('추천', '메뉴', '음식', '만들', '요리', '레시피', '먹을', '뭐', '무엇')
    )
    if not recommendation and not found:
        return None
    if not found:
        return []
    return [r for r, names in zip(recipes, ingredient_names)
            if (not categories or r['category'] in categories)
            and all(any(_matches_ingredient(term, name) for name in names) for term in found)]

def load_recipes(path):
    return _validate_recipes(json.loads(path.read_text(encoding='utf-8')))


def append_recipe(path, recipe):
    """기존 항목을 그대로 보존하고 검증이 끝난 파일만 게시합니다."""
    with FileLock(path.with_suffix('.json.lock'), timeout=5):
        original = path.read_bytes().rstrip()
        recipes = _validate_recipes(json.loads(original.decode('utf-8')))
        _validate_recipes([*recipes, recipe])
        separator = b',' if recipes else b''
        entry = json.dumps(recipe, ensure_ascii=False, indent=2).encode('utf-8')
        temporary_path = None
        try:
            with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
                temporary_path = temporary.name
                temporary.write(original[:-1].rstrip() + separator + b'\n' + entry + b'\n]\n')
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                os.unlink(temporary_path)


def _validate_recipes(recipes):
    if not isinstance(recipes, list):
        raise ValueError('레시피는 JSON 목록이어야 합니다.')
    ids = set()
    for recipe in recipes:
        if not isinstance(recipe, dict):
            raise ValueError('각 레시피는 JSON 객체여야 합니다.')
        for field in ('id', 'name', 'category', 'description', 'difficulty', 'image_note', 'tip'):
            if not isinstance(recipe[field], str) or not recipe[field].strip():
                raise ValueError(f'{field}: 비어 있지 않은 문자열이 필요합니다.')
        if not isinstance(recipe['image'], str):
            raise ValueError('image: 문자열이 필요합니다.')
        if recipe['id'] in ids:
            raise ValueError(f"중복 ID: {recipe['id']}")
        ids.add(recipe['id'])
        for field in ('time_minutes', 'servings'):
            if recipe[field] is not None and (type(recipe[field]) is not int or recipe[field] <= 0):
                raise ValueError(f'{field}: 양의 정수 또는 미기재(null)가 필요합니다.')
        if not isinstance(recipe['ingredients'], list) or not recipe['ingredients']:
            raise ValueError('재료 목록이 필요합니다.')
        for ingredient in recipe['ingredients']:
            if not isinstance(ingredient, dict):
                raise ValueError('각 재료는 JSON 객체여야 합니다.')
            if 'quantity_text' in ingredient:
                if not isinstance(ingredient['quantity_text'], str):
                    raise ValueError('재료 원문 분량은 문자열이어야 합니다.')
            else:
                if type(ingredient['amount']) not in (int, float) or not 0 < ingredient['amount'] < float('inf'):
                    raise ValueError('재료 수량은 유한한 양수여야 합니다.')
                if not isinstance(ingredient['unit'], str) or not ingredient['unit'].strip():
                    raise ValueError('재료 단위가 필요합니다.')
            for field in ('name',):
                if not isinstance(ingredient[field], str) or not ingredient[field].strip():
                    raise ValueError('재료 이름과 분량이 필요합니다.')
        if not isinstance(recipe['steps'], list) or not recipe['steps'] or any(not isinstance(s, str) or not s.strip() for s in recipe['steps']):
            raise ValueError('조리 순서는 비어 있지 않은 문자열 목록이어야 합니다.')
    return recipes
