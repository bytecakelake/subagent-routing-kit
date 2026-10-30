"""Build a proposal, not live Hermes configuration; no inference calls."""
import json, pathlib, sys, re, collections
P=pathlib.Path('/workspace/docs/subagent-rebuild')
sys.path.insert(0,'/hermes-home/skills/research/grounded-citations/scripts')
import sources
D={m['id']:m for m in json.loads((P/'openrouter-models-variants.json').read_text())['data']}
# name, tier, model, effort, latency intention (not measured), use, avoid
S=[
('F-Sol-Standard','프론티어','openai/gpt-6.1-sol','medium','균형','어려운 설계·근거 교차검증. 미들티어로 부족하지만 최대 추론까지 불필요한 작업','짧은 요약·단순 추출'),
('F-Sol-Deep','프론티어','openai/gpt-6.1-sol','high','정확성 우선','상충하는 제약·난해한 원인 분석·실패 비용이 큰 최종 검토','동일 과제 반복 재시도·시간 민감 단순 작업'),
('F-Sonnet-Code','프론티어','anthropic/claude-sonnet-5.5','medium','균형','여러 파일 구현·리팩터링·코드 리뷰. 작은 모델 실패 후 사용','한 줄 수정·대량 문서 정리'),
('F-Sonnet-Debug','프론티어','anthropic/claude-sonnet-5.5','high','정확성 우선','재현이 어려운 버그·복잡한 코드 경로·설계 결함 분석','범위가 좁은 기계적 코드 변경'),
('M-Terra-Quick','미들티어','openai/gpt-6.1-terra','low','저지연 지향','명확한 조건의 코드 탐색·일반 조사·작은 구현','불명확한 아키텍처·보안 최종 검토'),
('M-Terra-Balanced','미들티어','openai/gpt-6.1-terra','medium','균형','일반 다단계 구현·문서와 코드 종합 분석','단순 분류·최고 난도 최종 판정'),
('M-Terra-Deep','미들티어','openai/gpt-6.1-terra','high','정확성 우선','다수 제약·실패 원인 분석. 프론티어 승격 직전 단계','상시 기본값·대량 요약'),
('M-DeepSeekPro-Plain','미들티어','deepseek/deepseek-v4-pro','none','저지연 지향','명확한 요구사항의 코드 작성·형식 변환. 고급 모델을 비추론 모드로 비교할 실험','복잡한 설계·추론을 끈 상태의 난제'),
('M-DeepSeekPro-Reason','미들티어','deepseek/deepseek-v4-pro','high','정확성 우선','비용 제한을 고려한 깊은 코드 분석·구현·긴 문서의 논리 검토','추출·대량 분류. medium/low를 이 모델에 설정하지 말 것'),
('M-Haiku-Quick','미들티어','anthropic/claude-haiku-5.5','low','저지연 지향','입력 100K 미만의 검색 정리·요약·명확한 작은 수정','100K 이상 긴 입력·어려운 추론'),
('M-Haiku-Balanced','미들티어','anthropic/claude-haiku-5.5','medium','균형','기본 경로. 입력 100K 미만 일반 조사·작은 구현. 긴 입력이면 다른 경로 선택','100K 이상 무조건 배정·고위험 최종 판단'),
('M-Qwen-Lite','미들티어','qwen/qwen3.8-flash','none','저지연 지향','긴 자료의 단순 정리·비전 포함 추출. 추론 선택 미공개이므로 명시적으로 추론 끔','지원 미확인 low/medium/high 지정·깊은 추론'),
('L-GLM-Extract','로우티어','z-ai/glm-5.3-flash','low','저지연 지향','범위가 좁은 추출·분류·형식 변환·간단한 수정. 부모가 결과 확인','none/medium 임의 설정·중요한 무검증 변경'),
('Free-Nemotron-Visual','프리티어','nvidia/nemotron-3.5-super-vl:free','none','지연 허용','무료 이미지·텍스트 추출 실험. 추론을 명시적으로 끔. 유료 폴백 없음','납기 민감·개인정보·고위험 판단'),
('MM-MiMo-Inspect','멀티모달','xiaomi/mimo-v2.6-flash','none','저지연 지향','단순 화면·차트·이미지 내용 추출. 추론 강도 미공개여서 추론 끔','깊은 시각 추론·직접 음성/영상 전달 가정'),
('MM-Gemini-Inspect','멀티모달','google/gemini-4-argon','low','저지연 지향','저가 시각 모델이 놓친 복잡한 차트·문서·화면 분석','대량 단순 OCR·고급 추론을 요구하는 복합 도표'),
('MM-Gemini-Reason','멀티모달','google/gemini-4-argon','high','정확성 우선','여러 도표·이미지의 관계 추론·시각적 모순 검증','단순 이미지 설명·비용 제한 없는 장시간 분석')]

def problems(o):
    errors=[]
    m=D.get(o.get('model'))
    if not m: return ['unknown model']
    if 'tools' not in m.get('supported_parameters',[]):errors.append('tools unsupported')
    e=o.get('reasoning_effort')
    r=m.get('reasoning',{})
    if e is None:errors.append('implicit reasoning inheritance forbidden')
    elif e=='none':
        if r.get('mandatory') or 'reasoning' not in m.get('supported_parameters',[]):errors.append('cannot disable reasoning')
        # In Hermes 'none' is translated into reasoning.enabled=false, not invented effort selection.
    elif not isinstance(r.get('supported_efforts'),list) or e not in r['supported_efforts']:
        errors.append('unadvertised effort')
    if o.get('service_tier')!='normal':errors.append('OpenRouter fast/ultrafast not supported by installed Hermes service-tier gate')
    if o.get('fallback_providers')!=[]:errors.append('fallback policy not explicit')
    allowed={'name','description','provider','model','reasoning_effort','service_tier','fallback_providers'}
    if set(o)-allowed:errors.append('unrecognized model_map route keys')
    return errors

options=[]; specs=[]
for name,tier,mid,eff,intent,use,avoid in S:
    desc=f'{use}。避ける/금지: {avoid}. 추론={eff}; 속도=normal({intent}, 실측 전).'
    desc=desc.replace('。避ける/금지:', '. 사용 금지:')
    o=dict(name=name,description=desc,provider='openrouter',model=mid,reasoning_effort=eff,service_tier='normal',fallback_providers=[])
    assert not problems(o),(name,problems(o))
    options.append(o)
    m=D[mid]
    specs.append(dict(name=name,tier=tier,model=mid,reasoning_effort=eff,reasoning_wire='enabled=false' if eff=='none' else ('verbosity='+eff if mid.startswith('anthropic/') else 'reasoning.effort='+eff),service_tier='normal',latency_intent=intent,latency_measured=False,use_when=use,avoid_when=avoid,input_per_million=float(m['pricing']['prompt'])*1e6,output_per_million=float(m['pricing']['completion'])*1e6))
assert len(options)==len({o['name'] for o in options})
proposal={'options':options,'default':'M-Haiku-Balanced'}
B=pathlib.Path('/workspace/backups/subagent-rebuild'); B.mkdir(exist_ok=True,parents=True)
for fn in ['model-map-proposal.json','openrouter-subagent-rebuild-plan.md']:
    prev=P/fn; backup=B/(fn+'.v1')
    if prev.exists() and not backup.exists():backup.write_bytes(prev.read_bytes())
(P/'model-map-proposal.json').write_text(json.dumps(proposal,ensure_ascii=False,indent=2)+'\n')
(P/'variant-specs.json').write_text(json.dumps(specs,ensure_ascii=False,indent=2)+'\n')

# Validate rejection of previously problematic patterns; this is an offline guard, not endpoint inference.
checks=[]
def check(name,ok):
    checks.append({'name':name,'passed':bool(ok)})
    assert ok,name
check('all-proposed-routes-pass',all(not problems(o) for o in options))
base=options[0]
check('reject-implicit-effort',bool(problems({k:v for k,v in base.items() if k!='reasoning_effort'})))
check('reject-openrouter-fast',bool(problems({**base,'service_tier':'fast'})))
check('reject-openrouter-ultrafast',bool(problems({**base,'service_tier':'ultrafast'})))
check('reject-GLM-medium',bool(problems({**base,'model':'z-ai/glm-5.3-flash','reasoning_effort':'medium'})))
check('reject-GLM-disable',bool(problems({**base,'model':'z-ai/glm-5.3-flash','reasoning_effort':'none'})))
check('reject-DeepSeekPro-medium',bool(problems({**base,'model':'deepseek/deepseek-v4-pro','reasoning_effort':'medium'})))
check('reject-Kimi-medium',bool(problems({**base,'model':'moonshotai/kimi-k3.1-pro','reasoning_effort':'medium'})))
check('reject-Qwen-invented-effort',bool(problems({**base,'model':'qwen/qwen3.8-flash','reasoning_effort':'high'})))
check('reject-MiMo-invented-effort',bool(problems({**base,'model':'xiaomi/mimo-v2.6-flash','reasoning_effort':'medium'})))
check('reject-unsupported-extra-body-field',bool(problems({**base,'extra_body':{'provider':{'sort':'latency'}}})))
check('default-is-declared',proposal['default'] in {o['name'] for o in options})

# Exercise actual stdlib-importable installed conversion functions without modifying Hermes.
sys.path.insert(0,'/hermes-home/hermes-agent')
from hermes_constants import parse_reasoning_effort
from tools.delegate_tool_tuning import task_service_tier
from types import SimpleNamespace
check('actual-none-means-disabled',parse_reasoning_effort('none')=={'enabled':False})
pin=task_service_tier('normal',{'provider':'openrouter','model':'qwen/qwen3.8-flash','request_overrides':{'service_tier':'priority','extra_body':{'speed':'fast','retain':1}}},SimpleNamespace())
check('actual-normal-clears-inherited-speed',pin['request_overrides']=={'extra_body':{'retain':1}} and pin['service_tier'] is None)
# Compile the installed inheritance function unmodified, avoiding imports of unrelated optional dependencies.
import ast, typing, logging
src=pathlib.Path('/hermes-home/hermes-agent/tools/delegate_tool_config.py').read_text()
tree=ast.parse(src); nodes=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in ['ResolvedReasoning','_child_reasoning']]
ns={'NamedTuple':typing.NamedTuple,'Optional':typing.Optional,'Any':typing.Any,'logger':logging.getLogger('probe')}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'installed-inheritance-function','exec'),ns)
parent=SimpleNamespace(reasoning_config={'enabled':True,'effort':'high'})
check('actual-missing-route-inherits-global',ns['_child_reasoning'](parent,{'reasoning_effort':'medium'},None)=={'enabled':True,'effort':'medium'})
check('actual-missing-route-inherits-parent',ns['_child_reasoning'](parent,{},None)==parent.reasoning_config)
check('actual-explicit-none-blocks-inheritance',ns['_child_reasoning'](parent,{'reasoning_effort':'medium'},'none')=={'enabled':False})
(P/'variant-validation.json').write_text(json.dumps({'kind':'offline catalog guards + installed conversion-function probes, NOT inference','checks':checks,'passed':sum(c['passed'] for c in checks),'count':len(checks),'routes':len(options),'unique_models':len({o['model'] for o in options})},ensure_ascii=False,indent=2)+'\n')

L=['# OpenRouter 서브에이전트: 모델 × 작업용 변형 재구성안','',
'## 현재 단계와 범위','',
'2026-10-30. 모델 목록 중심 v1을 폐기하고 모델 × 변형 × 적용 조건 중심으로 개정했다. 현재 단계: 정적 호환성·설정 변환 검증 완료, 실호출 및 적용 전. default 프로필의 운영 설정은 변경하지 않았다. 다른 Hermes 프로필·대화·기억·스킬은 초기화하지 않는다.',
'Pro 명칭은 제외 기준이 아니다. Kimi Pro 비선호 이유는 작업 난도 대비 가성비였다. 모든 모델은 성공한 작업당 총비용으로 판단한다. 변형은 별도 계정/프로필이 아니라 model_map 경로다.','',
'## 설계의 핵심 수정','',
'1. **생략은 기본값 보장이 아니다.** 설치된 `tools/delegate_tool_config.py::_child_reasoning`은 경로 effort → delegation 전역 effort → 부모 reasoning_config 순으로 상속한다. 따라서 reasoning_effort가 빠진 경로를 안전한 네이티브 기본값으로 표시하지 않는다.',
'2. **추론 강도와 가속 서비스는 다르다.** low는 사고량을 낮추려는 설정이지 fast 서비스 구매가 아니다. 현재 설치된 Hermes `hermes_cli/models.py::_fast_mode_route_supported`는 일반 OpenRouter 경로의 fast/ultrafast를 허용하지 않는다. 모든 실행 제안에는 `service_tier: normal`을 명시한다. 이는 부모의 priority/speed 상속 제거이며, OpenRouter 내부 provider가 반드시 특정 표준 endpoint로 고정된다는 뜻은 아니다.',
'3. **강도 선택 미공개 모델을 임의의 Deep/Quick으로 복제하지 않는다.** Qwen Flash·MiMo Flash·무료 Nemotron VL은 공개 목록에 reasoning은 있지만 supported_efforts가 없다. 명시적인 추론 끄기만 선택한 제한형 변형으로 두고, 추론 켜기/네이티브 기본 모드는 별도 호환성 검증 전 보류한다.[1][6]',
'4. **none은 자동이 아니라 추론 끄기다.** Hermes는 none을 reasoning.enabled=false로 변환한다. 추론 필수 모델에는 none을 쓰지 않는다. none 경로의 첫 응답·도구 왕복 실호출은 아직 미검증이다.[6]',
'5. **표에 적힌 속도는 목표다.** 저지연 지향/균형/정확성 우선은 사용 목적이며 실측 초·tokens/s를 뜻하지 않는다. 짧은 사고가 항상 짧은 완료시간을 보장하지 않는다.','',
f'## 실행 후보: {len(options)}개 변형 / {len({o["model"] for o in options})}개 모델','',
'모든 변형의 속도 옵션은 normal, 유료/다른 모델 자동 폴백은 없음이다. 추천 기본값은 M-Haiku-Balanced(입력 100K 미만)이며 긴 입력은 부모가 다른 경로를 명시적으로 선택한다. 이하 배정은 실무 가설이고 성능 검증 결과가 아니다.','',
'| 티어 | 변형 경로 | 추론 | 속도 목표 | 언제 사용 | 사용하지 말 것 |','|---|---|---|---|---|---|']
for s in specs:L.append(f'| {s["tier"]} | `{s["name"]}` | {s["reasoning_effort"]} | {s["latency_intent"]} | {s["use_when"]} | {s["avoid_when"]} |')
L+=['','## 모델 ID·가격·지원 추론 강도','',
'가격은 USD / 100만 토큰 입력·출력, 비캐시 일반 모델 목록 기준. 업체별 단가·할인·긴 문맥 할증은 별도다. 같은 모델의 변형은 기본 단가가 같아도 소비 추론 토큰·도구 왕복 수가 달라 총비용이 달라진다. 추론 토큰은 출력 비용으로 청구된다.[1][6]','',
'| 모델 ID | 입력 / 출력 | 공개된 강도 | 정책 |','|---|---:|---|---|']
for mid in dict.fromkeys(o['model'] for o in options):
    m=D[mid]; r=m.get('reasoning',{}); es=r.get('supported_efforts'); efforts='/'.join(es) if isinstance(es,list) else '선택 강도 미공개'; policy='추론 필수' if r.get('mandatory') else '추론 끄기 가능(실호출 검증 전)'
    L.append(f'| `{mid}` | ${float(m["pricing"]["prompt"])*1e6:g} / ${float(m["pricing"]["completion"])*1e6:g} | {efforts} | {policy} |')
L+=['','Haiku는 100K 이상 입력 시 $0.50/$2.50으로 할증된다. Sol·Terra는 272K 입력 기준 할증이 있으므로 긴 컨텍스트와 저렴한 문서 처리를 혼동하지 않는다. GLM Flash와 DeepSeek Pro는 특히 provider별 단가 편차를 확인해야 한다.[1]',
'Haiku와 Sonnet은 설치된 OpenRouter 어댑터에서 reasoning.effort 대신 top-level verbosity로 강도를 전달하는 분기가 있다. API body를 자체 제작할 때 Hermes 설정 키를 그대로 전송하는 방식으로 검증했다고 주장하지 않는다.','',
'## Kimi Pro 등 예비 변형','',
'| 변형 | 모델 | 추론 | 속도 | 사용 조건 / 보류 이유 |','|---|---|---|---|---|',
'| Reserve-Kimi-Visual | moonshotai/kimi-k3.1-pro | high | normal | 긴 시각/코드 복합 과제에서 Sol/Sonnet 대비 재작업을 줄이는지 확인할 때. 입력 $2/출력 $10 |',
'| Reserve-Kimi-Quick | moonshotai/kimi-k3.1-pro | low | normal | 비싼 모델의 사고량을 줄여도 작업 이점이 유지되는지 비교할 때. 저가 작업의 기본값으로 사용 금지 |',
'| Reserve-Opus-Deep | anthropic/claude-opus-5.5 | high | normal | 실패 비용이 큰 최난도 작업에서만. 입력 $4/출력 $20 |',
'| Reserve-DeepSeekFlash-Low/High | deepseek/deepseek-v4.1-flash-1017 | low / high | normal | 저비용 도구 작업 비교군. medium이 공개 강도 목록에 없으므로 중간값을 발명하지 말 것 |',
'| Hold-MiMoPro-Native | xiaomi/mimo-v2.6-pro | 네이티브 모드 격리 미확인 | normal | 이름이 Pro라서 제외하는 것이 아니다. 강도 미공개·상속 차단·기본 추론 모드 검증이 선행되어야 함 |',
'| Hold-Flint-Native | recursive/flint-v1.0:free | 필수 추론, 강도 미공개 | normal | none으로 끌 수 없고 생략하면 상속되므로 네이티브 기본값 격리 경로 확인 전 보류 |',
'| Hold-Qwen-Deep / MiMo-Deep / Omni-Deep | 각 Flash 모델 | 미확인 | normal | reasoning 지원과 low/medium/high 선택 지원은 별개. 가짜 변형을 등록하지 말 것 |',
'Kimi의 표준 endpoint는 $2/$10, 별도 highspeed endpoint는 $4/$20이다. 그러나 OpenRouter에 highspeed endpoint가 있다는 사실과 Hermes model_map의 service_tier:fast 사용 가능 여부는 별개다. 이번 제안에는 Highspeed 변형을 등록하지 않는다.[8]',
'DeepSeek V4 Pro는 표준 목록상 약 $0.816/$1.632다. 정확한 ID 엔드포인트에서 도구 지원을 확인하여 Pro 배제 없이 미들티어 추론 후보로 편입했다. 가격이 싸다는 이유로 성능 동등성을 가정하지는 않는다.[1][9]','',
'## 속도 옵션을 다루는 정책','',
'- `service_tier: normal`: 현 설치에서 허용되는 상속 차단용 설정. 이번 제안의 공통값이다.',
'- `service_tier: fast/ultrafast`: OpenRouter 경로에서는 현 Hermes 게이트와 맞지 않아 금지한다. 다른 provider에서 가능한 옵션을 그대로 옮기지 않는다.',
'- OpenRouter provider.sort=latency/throughput 및 endpoint only는 별도의 라우팅 제어다. low reasoning과도 별개다. 라우팅은 속도를 선호할 뿐 SLA를 보장하지 않는다.[7]',
'- 현재 advanced-delegation model_map의 ROUTE_FIELDS에는 extra_body/provider_preferences/request_overrides가 없다. 여기에 임의의 provider.sort JSON을 넣어도 전달되지 않으므로 설정 파일에 가짜 필드를 추가하지 않는다. 실제 속도 기반 endpoint 변형은 지원되는 provider 경로 또는 플러그인 확장 설계·검증이 필요하며 이번에는 코어/플러그인을 수정하지 않았다.',
'- 최초 토큰까지 시간(TTFT), 가시 출력 tokens/s, 전체 완료시간, 도구 왕복 수, 재시도를 따로 측정한다. 이번 공개 endpoint 응답에는 비교 가능한 latency/throughput 수치가 없어 임의의 초·속도 배수를 쓰지 않는다.','',
'## 작업 선택·승격 규칙','',
'1. 단순 추출/변환 → L-GLM-Extract. 실패가 문맥/추론 문제이면 Haiku/Terra로 승격한다.',
'2. 짧은 일반 작업 → M-Haiku-Quick 또는 Balanced. 100K 이상이면 Qwen-Lite(단순) 또는 DeepSeekPro-Reason/Terra(추론)로 분기한다.',
'3. 일반 구현 → Terra-Quick/Balanced. 조건 충돌·원인 분석이 추가되면 같은 모델 Deep으로 한 단계 올린다.',
'4. 비용 민감한 깊은 코드 작업 → DeepSeekPro-Reason과 Terra-Deep을 비교한다. 실패 시 반복 소모하지 말고 Sonnet-Debug/Sol-Deep으로 승격한다.',
'5. 시각 추출 → MiMo-Inspect 또는 무료 Nemotron. 복잡한 시각 관계는 Gemini-Inspect/Reason. Hermes의 직접 미디어 전달은 이미지 최대 8개이며 음성/영상은 별도 전처리·도구 경로가 필요하다.[3]',
'6. 비싼 모델은 저가 모델의 반복 실패 비용을 줄일 때만 채택한다. Kimi는 Pro 명칭으로 제외하지 않되 이 개선을 실측하기 전 상시 기본값으로 두지 않는다.',
'7. 무료 실패는 유료 자동 전환하지 않는다. 무료 요청 제한 때문에 무료 티어에 납기를 의존하지 않는다.[2]','',
'## 검증 결과와 남은 인수 조건','',
f'- 오프라인 검사 {len(checks)}개 통과: 모델/강도/필수 추론/속도/기본값/필드 화이트리스트 + 설치된 none·normal 설정 변환 + 상속 함수 재현. `variant-validation.json` 참조.',
'- 검증한 부정 사례: Kimi medium, DeepSeek Pro medium, GLM Flash medium/none, Qwen/MiMo 임의 high/medium, OpenRouter fast/ultrafast, model_map의 가짜 extra_body, effort 생략을 모두 제안 검증기에서 거부한다.',
'- 부정 사례 거부는 오프라인 검증기 동작이며 실제 endpoint에 잘못된 유료 요청을 보낸 결과가 아니다. provider가 옵션을 받아들여도 실제 동작을 무시할 수 있으므로 실호출이 최종 검증이다.',
'- live config는 무변경이다. Docker에 호스트 hermes CLI가 없으므로 운영 적용·신규 경로 호출은 수행하지 않았다.',
'- 다음 적용 전: 경로마다 짧은 응답 → 강제 도구 호출 → 도구 결과 반영 → 구조화 출력 → 시각 경로 이미지 판독을 실행한다. 성공 응답의 provider/model/실제 wire 옵션, 비용·reasoning tokens·시간·재시도를 기록한다.',
'- 같은 모델 Quick/Balanced/Deep을 동일 과제로 비교하여 강도 차이가 실제 소비·품질에 반영되는지 확인한다. none은 enabled=false로 전달되고 fast/speed 키가 요청에 남지 않는지도 확인한다.',
'- 옵션 변경은 새 세션에서 반영하고 설정 read-back 및 option enum을 확인한다. 대화 중 도구 스키마를 강제로 바꾸지 않는다.[3]','',
'## 산출물 및 적용 범위','',
'- `model-map-proposal.json`: 기존 제안 대체. 실행 후보 경로만 포함, 기본값 M-Haiku-Balanced. 모두 normal·명시적 effort·자동 폴백 없음.',
'- `variant-specs.json`: 모델별 변형의 역할·금지 조건·목표 속도·wire 변환·가격. 실제 설정 JSON과 구분한다.',
'- `variant-validation.json`: 오프라인 검증 결과. 실호출 결과와 혼동하지 말 것.',
'- `openrouter-models-variants.json`: 최신 공개 모델 목록 원본.',
'- `variant-extra-endpoints.json`: Kimi Pro·DeepSeek Pro·Gemini Argon·MiMo Pro 정확한 ID endpoint 응답.',
'- 이전 v1 문서/제안은 `/workspace/backups/subagent-rebuild/`에 보관했다. 이전 build_proposal.py가 아닌 build_variants.py가 현재 제안 생성기다.','',
'## 지금 달성한 것 → 다음 단계','',
'모델명 기반 추천을 작업별 변형 체계로 개정·옵션 상속 및 속도 제약 발견·오프라인 검증 완료 → 실호출 예산/범위 확정 후 endpoint·도구 왕복 검증을 통과한 경로만 운영 적용.']
existing_report=P/'openrouter-subagent-rebuild-plan.md'
taxonomy_heading='## 운영 티어 세분화 제안 — 모델 서열과 호출 정책의 분리'
if existing_report.exists():
    previous=existing_report.read_text(encoding='utf-8')
    parent_heading='## 부모 모델과 실행자의 판단 분담'
    if parent_heading in previous:
        parent_start=previous.index(parent_heading)
        parent_end=previous.index('## 설계의 핵심 수정',parent_start)
        parent_pos=L.index('## 설계의 핵심 수정')
        L[parent_pos:parent_pos]=[previous[parent_start:parent_end].rstrip(),'']
    if taxonomy_heading in previous:
        start=previous.index(taxonomy_heading)
        end=previous.index('## 실행 후보:',start)
        pos=next(i for i,line in enumerate(L) if line.startswith('## 실행 후보:'))
        L[pos:pos]=[previous[start:end].rstrip(),'']
ledger=sources.load_ledger(P/'citations.json')['sources']; text='\n'.join(L)+'\n'; ids={int(x) for x in re.findall(r'\[(\d+)\]',text)}
text+='\n'+sources.render_sources(ledger,only=ids)+'\n'
report=P/'openrouter-subagent-rebuild-plan.md'; report.write_text(text,encoding='utf-8')
code,errors,warnings=sources.verify_draft(report,ledger)
assert code==0,errors
print(json.dumps({'routes':len(options),'models':len({o['model'] for o in options}),'tier_routes':dict(collections.Counter(s['tier'] for s in specs)),'offline_checks':len(checks),'passed':all(c['passed'] for c in checks),'citations':code,'default':proposal['default'],'live_config_changed':False},ensure_ascii=False,indent=2))
print('report',report)
