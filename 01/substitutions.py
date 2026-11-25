"""대체표 조회. 원본 레시피와 대체 데이터는 수정하지 않습니다."""
import json
import re
import unicodedata


def normalize(value):
    return re.sub(r'[\s·()]+', '', unicodedata.normalize('NFKC', value).casefold())


def load_substitutions(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    entries = data['substitutions']
    if not isinstance(entries, list):
        raise ValueError('대체표는 목록이어야 합니다.')
    ids = set()
    for entry in entries:
        for key in ('id', 'original', 'substitutes_text', 'usage', 'warning', 'allergens', 'verified', 'ratios'):
            if key not in entry:
                raise ValueError(f'대체 정보 필드 누락: {key}')
        if entry['id'] in ids:
            raise ValueError('대체 정보 ID가 중복됩니다.')
        ids.add(entry['id'])
    return entries


def find_substitutions(name, entries):
    term = normalize(name)
    if term.startswith('시판'):
        term = term[2:]
    return [e for e in entries if term in {normalize(e['original']), *(normalize(a) for a in e.get('aliases', []))}]


def substitution_chat_answer(prompt, entries):
    if not any(word in prompt for word in ('대체', '대신', '없으면', '없는데', '없어')):
        return None
    # 문장 전체에서 부분 일치하지 않고 조사로 끝나는 원래 재료를 먼저 찾습니다.
    compact = normalize(prompt)
    occurrences = []
    for e in entries:
        for name in [e['original'], *e.get('aliases', [])]:
            term = normalize(name)
            start = compact.find(term)
            if start >= 0:
                occurrences.append((start, -len(term), e))
    if not occurrences:
        return '등록된 소스 대체표에 해당 재료의 정보가 없습니다. 소스 대체표에서 원래 소스 이름을 확인해 주세요. 표에 없는 대체법이나 비율은 확인된 정보처럼 안내하지 않습니다.'
    occurrences.sort(key=lambda item: (item[0], item[1]))
    original = occurrences[0][2]['original']
    matches = [e for e in entries if e['original'] == original]
    # A를 B로 바꿀 수 있는지 묻는 경우 B가 등록 조합에 속하는지 확인합니다.
    target = re.search(r'(?:을|를)\s*(.+?)(?:으로|로)\s*(?:대체|바꿀|바꾸)', prompt)
    if target and not any(word in target[1] for word in ('뭐', '무엇', '어떤', '다른')):
        requested = normalize(target[1])
        relevant = [e for e in matches if requested in {normalize(component) for combination in option_combinations(e) for component in combination.split(' + ')}]
        if not relevant:
            return f'{original}을 요청하신 재료로 대체하는 방법은 등록된 표에서 확인되지 않습니다.\n\n등록 후보: ' + ' / '.join(e['substitutes_text'] for e in matches) + '\n\n모두 실제 조리 미검증 후보이며, 같은 맛이나 비율을 보장하지 않습니다.'
        matches = relevant
    lines = []
    for e in matches:
        name = e['original']
        final = ord(name[-1]) - 0xAC00
        particle = '은' if 0 <= final <= 11171 and final % 28 else '는'
        lines.append(f"{name}{particle} **{e['substitutes_text']}** 조합으로 대체할 수 있어요. "
                     f"이렇게 대체하면 **{', '.join(e['usage'])}**에 활용할 수 있어요.")
    return '\n\n'.join(lines)


def option_combinations(entry):
    """OR 대안을 실제 선택 가능한 조합으로 전개합니다."""
    from itertools import product
    variants = entry.get('alternative_combinations') or [{'substitutes': entry['substitutes']}]
    result = []
    for variant in variants:
        choices = [[item['name'], *(a['name'] for a in item.get('alternatives', []))] for item in variant['substitutes']]
        result.extend(' + '.join(parts) for parts in product(*choices))
    return list(dict.fromkeys(result))
