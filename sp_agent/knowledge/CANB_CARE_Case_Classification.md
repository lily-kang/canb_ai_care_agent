
## CANB_CARE 상담 CASE 분류 근거

본 문서는 시험/학습 활동 데이터 기반으로 12개의 메인 케이스와 4개의 초기 케이스를 판정하기 위한 정량적 근거를 정리합니다. 각 케이스는 핵심 조건과 참고/보조 조건으로 구성됩니다.

---

## 메인 케이스(12)

### 1) `STEADY_TOP` - 꾸준히 상위권 유지형
- 핵심 조건
  - 과목별 Below 없음(PIVOT)
  - `PCT ≤ 20%` (Overall 총 정답 수 기준, 상위 20% 이내)
  - `PCT_TR ∈ ['유지','상승']` (응시일 기준 성적 추세 안정)
  - `DIFF_GAP ∈ ['Low','Medium']` (문항 난이도별 정답률 차이 적음)
  - `ASGN_RATE ≥ 90` (이러닝 완료 우수)
  - `ASGN_TR ∈ ['유지','상승']` (due date 준수율 안정)
  - `SUBJ_DIFF ≤ 10` (과목별 총 정답률 간 편차 적음)
- 참고/보조 조건
  - `ASGN_Grade ≥ 85` (이러닝 전체 성취율)
  - `READ_CNT` 레벨 평균 이상
  - `LOW_DIFF_ERR_RATE` 낮음
  - `ABS_CNT` 결석 거의 없음
  - `DELTA_MEAN ≥ 0` (과거 평균 대비 유지 이상)
  - 과목별 Below 없음(PIVOT), Above 3개 이상(PIVOT), 시험 3회차 이상(PIVOT)

### 2) `SINGLE_DIP` - 특정 영역 일시 하락형
- 핵심 조건
  - `PCT ≤ 40%` (상위 40% 이내)
  - `PCT_TR ≠ '불안정'` (전체 성적 급변동 없음)
  - `SINGLE_DROP = True` (1개 과목 총 정답률만 급락)
  - `SESSION_DIFF ≤ 15` (회차 간 Overall 총 정답률 차이 크지 않음)
- 참고/보조 조건
  - `ASGN_Grade ≥ 80`
  - `ASGN_TR` 유지/상승
  - `READ_TR` 유지/상승
  - `READ_CNT` 평균 이상 유지
  - `LOW_DIFF_ERR_RATE` 양호
  - `DIFF_GAP`이 높은 경우 해당 과목 난이도 ‘상’ 오답 집중 여부 확인

### 3) `OVERALL_DIP` - 전체적으로 일시 하락형
- 핵심 조건
  - `PCT_TR = '하락'` (Overall 백분위/정답률 감소 추세)
  - 최근 `SCORE_CHG` -5 ~ -15 (직전 대비 하락)
  - `DELTA_MEAN < 0` (본인 평균 대비 하락)
  - `SUBJ_DIFF_TR` 변동 크지 않음
  - 과목별 Below/On/Above 판정 ∈ ['유지','하락'] (지난 시험 대비, PIVOT)
- 참고/보조 조건
  - `ASGN_TR` 하락 또는 `DUE_MISS` 증가
  - `ABS_TR` 결석 증가(단 `ABS_CNT`는 소수)
  - `READ_TR` 유지 또는 상승(독서는 무너지지 않음)
  - `LOW_DIFF_ERR_RATE` 소폭 상승하나 평균 근처
  - `ASGN_RATE` 하락했으나 75% 이상 유지

### 4) `STEADY_LOW` - 꾸준히 하위권 유지형
- 핵심 조건
  - `70% ≤ PCT` (상위 70% 이상)
  - `PCT_TR` 유지 또는 하락
  - `ASGN_RATE < 75%`
  - `ONLINE_GAP ≤ 20` (이러닝 점수 vs 테스트 총 정답률 괴리 적음)
- 참고/보조 조건
  - `DELTA_MEAN ≤ 0`
  - `READ_CNT` 저조 및 `READ_TR` 하락
  - `LOW_DIFF_ERR_RATE` 높음(기초 오답)
  - `SUBJ_DIFF` 작음(전반 기초 부족)
  - `ASGN_TR` 불규칙/낮은 수준
  - 과목별 Above 없음(PIVOT), Below 2개 이상(PIVOT), 시험 3회차 이상(PIVOT)

### 5) `GROWTH` - 성장형
- 핵심 조건
  - `PCT_TR = '상승'` (Overall 총 정답 수 지속 상승)
  - `CONSEC_IMP ≥ 2` (2회 이상 점수 향상)
  - 최근 `SCORE_CHG ≥ +5`
  - `DELTA_MEAN > 0` (본인 평균 상회)
- 참고/보조 조건
  - `ASGN_TR` 상승 (완료/기한 준수)
  - `SUBJ_DIFF_TR` 감소 또는 안정
  - `READ_TR` 상승
  - `LOW_DIFF_ERR_RATE` 감소 추세
  - `ABS_CNT` 적음
  - 과목별 판정 ∈ ['유지','상승'] (지난 시험 대비, PIVOT)

### 6) `UNSTABLE` - 불안정형
- 핵심 조건
  - `PCT_TR = '불안정'` (응시일별 등락 반복)
  - `SESSION_DIFF > 15` (회차 간 차이 큼)
  - `SUBJ_DIFF > 20` (과목별 격차 큼)
- 참고/보조 조건
  - `DIFF_GAP` 큰 편(난이도별 차이 큼)
  - `ASGN_TR` 불안정
  - `READ_TR` 변동폭 큼
  - `LOW_DIFF_ERR_RATE` 평균 대비 약간 높음(집중력 기복)
  - `ABS_TR` 특정 시기 결석 몰림

### 7) `TOP_WEAK_SKILL` - 고득점이지만 세부 취약 문제형
- 핵심 조건
  - `PCT ≤ 25%` (상위 25% 이내)
  - `DIFF_GAP = 'High'` (난이도 ‘상’ 오답률 높음)
  - `ASGN_TR`, `READ_TR` 안정적
- 참고/보조 조건
  - `READ_CNT` 상위권 유지
  - `LOW_DIFF_ERR_RATE` 낮음(기본기 탄탄)
  - 오답 보기 선택률: 고난도 문제 오답 집중
  - `DELTA_MEAN ≥ 0` (이력 양호)
  - `SESSION_DIFF` 큼, `SUBJ_DIFF` 작음

### 8) `MOTIVATION_DROP` - 성적은 유지되나 의욕 저하형
- 핵심 조건
  - `PCT_TR = '유지'` (Overall 총 정답률 유지)
  - `ASGN_TR = '하락'` (수행 간격 증가·완료 감소)
  - `READ_TR = '하락'`
  - `DELTA_MEAN` 소폭 하락 또는 유지
- 참고/보조 조건
  - `READ_CNT` 과거 대비 감소
  - `ASGN_RATE` 75% 전후(버티기)
  - `LOW_DIFF_ERR_RATE` 평균 수준
  - `ABS_TR` 소폭 결석 증가 가능
  - `ONLINE_GAP` 격차 축소/악화

### 9) `MID_PLATEAU` - 중간권 정체형
- 핵심 조건
  - `30% ≤ PCT < 55%` (중위권)
  - `PCT_TR = '유지'` (변동 없음)
  - `ASGN_RATE` 75~84%
  - `READ_TR` 유지
- 참고/보조 조건
  - `DIFF_GAP` ‘Medium’/‘High’ (고난도 취약)
  - `READ_CNT` 평균
  - `LOW_DIFF_ERR_RATE` 낮음(기초 양호)
  - `SUBJ_DIFF` 크지 않음
  - `DELTA_MEAN` 변동 없음
  - `CONSEC_IMP` 1회 이하

### 10) `SPARK` - 단기 급등형
- 핵심 조건
  - `PCT_TR = '급상승'` (전 회차 대비 급증)
  - 최근 `SCORE_CHG ≥ +10`
  - `DELTA_MEAN ≥ +15` (평균 대비 급등)
- 참고/보조 조건
  - `ASGN_TR`, `READ_TR` 상승
  - `READ_CNT` 레벨 평균 상회
  - `ASGN_RATE ≥ 80%`
  - `LOW_DIFF_ERR_RATE` 급감
  - `SESSION_DIFF` 큼(긍정적 방향)
  - `PCT` 중하위권 → 상위권 점프

### 11) `TEST_ANXIETY` - 시험불안형
- 핵심 조건
  - `ASGN_RATE ≥ 85%` (이러닝 완료 우수)
  - `ONLINE_GAP > 20` (이러닝 vs 테스트 괴리 큼)
  - `LOW_DIFF_ERR_RATE` 높음(난이도 ‘하’에서도 오답)
- 참고/보조 조건
  - `PCT < 55%` (중위권 이상)
  - `READ_TR`, `READ_CNT` 우수(노출량 충분)
  - `ABS_CNT` 적음
  - `PCT_TR` 특정 회차 급락 패턴
  - 소요 시간(테스트 Raw) 과단/과장 → 시간 관리 이슈 점검

### 12) `DISENGAGED` - 학습의욕 상실형
- 핵심 조건
  - `PCT_TR = '하락'` (지속 감소)
  - `ASGN_TR = '하락'` (완료 감소)
  - `READ_TR = '하락'` (독서 감소)
  - `ABS_TR = '상승'` (결석 증가)
- 참고/보조 조건
  - `DELTA_MEAN` 감소
  - `SUBJ_DIFF_TR` 증가
  - `DUE_MISS` 증가 추세
  - `READ_CNT` 현저 감소
  - `LOW_DIFF_ERR_RATE` 증가
  - `ONLINE_GAP` 커짐(이러닝·시험 동반 하락)
  - 과목별 Below 판정 증가(PIVOT)

---

## 초기 케이스(4)

### `INIT_HIGH` - 초기 우수형
- 핵심 조건(첫 시험)
  - `PCT ≤ 20%` (상위 20% 이내)
  - `ASGN_RATE ≥ 85%`
  - `LOW_DIFF_ERR_RATE` 낮음
  - `ONLINE_GAP ≤ 20` (이러닝/테스트 일치)
- 참고/보조 조건
  - `ABS_CNT ≤ 1` (결석 거의 없음)
  - `READ_CNT` 레벨 평균 이상
  - `SUBJ_DIFF` 작음 (과목/스킬 간 편차 적음)

### `INIT_STABLE` - 초기 안정형
- 핵심 조건(첫 시험 + 이러닝)
  - `20% < PCT ≤ 40%` (상위 20~40%)
  - `ASGN_RATE ≥ 80%`
  - `LOW_DIFF_ERR_RATE` 낮음
  - `ONLINE_GAP ≤ 20`
- 참고/보조 조건
  - `ABS_CNT` 결석 적음
  - `READ_CNT` 평균 수준
  - `DIFF_GAP` ‘Medium’/‘High’ (난이도 ‘상’에서 오답 발생)

### `INIT_ANXIETY` - 초기 긴장형
- 핵심 조건(온라인 우수/테스트 저조)
  - `40% < PCT ≤ 55%` (상위 40~55%)
  - `ASGN_RATE ≥ 80%`
  - `ONLINE_GAP > 20`
  - `LOW_DIFF_ERR_RATE` 높음(난이도 ‘하’ 오답)
- 참고/보조 조건
  - `ABS_CNT ≤ 1` (결석 없음에 가깝게)
  - `DIFF_GAP` 크지 않음(실수 영향)
  - `READ_CNT` 양호

### `INIT_FOUNDATION` - 초기 기초다지기형
- 핵심 조건(전반 저조)
  - `PCT > 55%`
  - `ASGN_RATE < 75%`
  - `LOW_DIFF_ERR_RATE` 높음(난이도 ‘하’ 오답 다수)
- 참고/보조 조건
  - `SUBJ_DIFF` 작음(전반 기초 부족)
  - `READ_CNT` 부족
  - `ONLINE_GAP ≤ 20` (이러닝/테스트 모두 낮음)
