# routing-guard (Hermes 플러그인)

`delegate_task` 가 실행되기 **전에** 선택된 `model_map` 경로를 하드 규칙으로 검사하고, 위반이면 호출을 막습니다. 판정은 `core/eligibility` 규칙을 그대로 쓰며, 모델 추천이나 부모의 즉흥 판단으로 우회되지 않습니다.

## 무엇을 막는가

| 규칙 | 차단 조건 |
|---|---|
| 등록 | `delegation.backends.model_map.options` 에 없는 이름 |
| 추론 강도 | 생략(상속), 모델이 공개하지 않은 값, 추론 필수 모델의 `none` |
| 속도 | `normal` 이 아닌 미검증 단계 |
| 무료→유료 | 무료 모델인데 `fallback_providers` 가 비어 있지 않음 |
| 모달리티 | 이미지 작업인데 모델이 이미지를 받지 못함 |
| 도구 | 도구를 지원하지 않는 모델에 도구 작업 배정 |
| 컨텍스트 | 입력 길이를 알 때 컨텍스트 초과 |
| 능력 정보 없음 | 스냅샷에 없는 모델 (`strict_unknown_model: false` 면 경고만) |

차단 메시지에는 위반 코드와 **대안 경로**(기본 경로 우선)가 함께 나가므로, 부모가 곧바로 다른 경로로 재시도할 수 있습니다. 입력 길이는 `delegate_task` 인자에 없으므로 이 가드는 길이 기반 규칙을 경고 없이 건너뜁니다.

## 설치

```powershell
$src = "C:\Users\BCL\HermesWorkspace\projects\subagent-routing-kit\adapters\hermes\plugin\routing-guard"
$dst = "$env:LOCALAPPDATA\hermes\plugins\routing-guard"
Copy-Item -Recurse -Force $src $dst
```

`plugins.enabled` 는 허용 목록이므로 이름을 추가해야 로드됩니다. 현재 목록에 `routing-guard` 를 더해 그대로 설정하십시오.

```powershell
hermes config set plugins.enabled '["advanced-delegation","disk-cleanup","model-leaderboard","openrouter-picker","security-guidance","routing-guard"]'
hermes gateway restart -y
```

재시작 후 로그에 `routing-guard 활성` 이 보이면 로드된 것입니다.

## 설정

`plugins.entries.routing-guard.settings` 아래에 둡니다.

| 키 | 기본 | 뜻 |
|---|---|---|
| `strict_unknown_model` | `true` | 능력 스냅샷에 없는 모델도 차단. `false` 면 경고만 남기고 통과 |
| `capabilities_path` | 빈 값 | 비우면 플러그인 폴더의 `capabilities.json` |

## 검증

1. 정상 호출은 그대로 통과하는지: 17개 경로 중 아무거나 `delegate_task` 로 실행.
2. 차단이 실제로 걸리는지: `delegation.backends.model_map.options` 에서 한 경로의 `reasoning_effort` 를 `none` 으로 잠시 바꾼 뒤(예: `L-GLM-Extract`) 그 경로로 위임 → 차단 메시지와 대안 목록이 와야 합니다. 확인 후 원래 값으로 되돌리십시오.
3. 되돌리기: `config.yaml` 백업을 복사하고 재시작.

## 한계

- `delegate_task` 인자에 없는 정보(입력 토큰 수, 승인 필요 여부, 위험도, 쓰기 범위)는 판정에 쓰지 못합니다. 그래서 길이 할증·승인 규칙은 런타임에서 강제되지 않습니다.
- 능력 데이터는 스냅샷입니다. 새 모델을 추가하면 `python adapters/hermes/sync_plugin.py` 로 갱신해야 하며, 갱신 전에는 `strict_unknown_model: true` 인 경우 그 경로가 차단됩니다.
- 가드 자체에 예외가 나면 **통과시키고 경고 로그를 남깁니다**. 버그로 모든 위임이 막히는 쪽이 더 위험하기 때문입니다. 로그에서 `routing-guard: 검사에 실패해` 를 확인하십시오.
- 이 플러그인은 `model_map` 백엔드에만 관여합니다. `default`·`profile_routes` 백엔드에서는 아무것도 하지 않습니다.
