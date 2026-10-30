# 라우팅 정책: 작업 티어와 실제 활성 경로의 연결

이 표는 `core/spec/variant-specs.json`의 변형 이름에 작업 티어를 연결하는 제안 매핑이다. 등록 증거가 아니다. 현재 위임 도구에 등록된 경로와 실행 설정이 우선한다. 과거 별칭에서 아래 이름으로 자동 치환하지 않는다.

| 정책 | 작업 | 제안 경로 우선 후보 |
|---|---|---|
| L1 | 좁은 추출·분류·변환 | L-GLM-Extract; 긴 단순 입력 M-Qwen-Lite |
| L2 | 범위·테스트가 명확한 작은 수정 | M-Haiku-Quick; M-DeepSeekPro-Plain |
| M1 | 일반 다단계 조사·구현 | M-Haiku-Balanced(100K 미만); M-Terra-Quick; M-Terra-Balanced |
| M2 | 심층 논리·코드 분석 | M-DeepSeekPro-Reason; M-Terra-Deep |
| F1 | 전문 설계·코드 구현·교차검증 | F-Sol-Standard; F-Sonnet-Code |
| F2 | 난제·고위험 검토 | F-Sol-Deep; F-Sonnet-Debug |
| F3 | 최고 난도 예외 | 미등록 예비. Opus/Kimi를 이름만 보고 호출하지 말 것 |
| E0 | 지연/실패 허용 무료 실험 | Free-Nemotron-Visual |
| V1 | 시각 판독 | MM-MiMo-Inspect; 부족하면 MM-Gemini-Inspect |
| V2 | 시각 관계·모순 추론 | MM-Gemini-Reason |

## 모델 변형 해석

- Sol Standard=medium / Deep=high.
- Sonnet Code=medium / Debug=high.
- Terra Quick=low / Balanced=medium / Deep=high.
- DeepSeek V4 Pro Plain=none / Reason=high. low/medium 임의 지정 금지.
- Haiku Quick=low / Balanced=medium. 입력 100K 이상 할증 구간에 무조건 배정하지 말 것.
- Qwen Lite=none; GLM Extract=low; 무료 VL=none; MiMo Inspect=none.
- Gemini Inspect=low / Reason=high.
- 모두 현 제안의 service_tier=normal. 저지연 목표와 fast 서비스 지원을 혼동하지 말 것.
- 추론 끄기 경로와 신규 모델 변형의 실호출은 별도 검증 대상이다. 표가 live 검증을 대체하지 않는다.

## 선택 체크

1. 직접 도구 / 단일 자식 / 독립 병렬 / 순차 실행을 먼저 선택한다.
2. 작업 유형·변경 위험·입력 규모·지연/비용 제약으로 티어를 고른다.
3. 현재 등록된 경로 목록의 정확한 이름과 실제 모델, 추론 강도, 속도를 대조한다.
4. 제안 이름이 없거나 설정이 다르면 activation_required로 중단한다. 부모가 직접 처리 가능한 부분은 진행한다.
5. 경로 목록이 세션 시작 시 고정되는 프레임워크라면 새 설정을 적용한 뒤 새 세션에서 재확인한다.

현재 모델 가격이나 실측 속도는 이 파일에 복제하지 않는다. 필요한 시점에 원본 가격과 엔드포인트, 검증 기록을 확인하여 오래된 데이터를 피한다.
