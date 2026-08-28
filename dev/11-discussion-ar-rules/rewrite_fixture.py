from __future__ import annotations

import json
from pathlib import Path


TARGET = Path("data/synthetic/emails/discussion-email-ar-rules/discussion-email-ar-rules.json")

SCENARIOS = [
    dict(project="동부허브 자동분류기 구동부 교체공사", request="동부허브 운영기획팀 한가람", vendor="한빛모션", initial="100,000,000원", initial_qty="구동부 4세트", scope="구동부 교체와 기본 시운전", location="동부허브 1층 자동분류 3번 라인", schedule="2026년 9월 19일", reason="반복되는 순간 정지로 출고 처리량이 떨어질 위험", cost="동부허브 설비개선 비용센터", review="안전환경팀은 작업 동선과 전원 차단 방식을, 구매팀은 기존 투자계획 승인액과 견적 조건을 확인해 주시기 바랍니다.", safety="시설안전팀 오세린", safety_change="작업 위치를 통행로 쪽에서 서측 점검구 안쪽으로 옮기고 방진 브래킷과 이중 안전펜스를 추가", safety_reason="지게차 통행과 정비 인력이 교차하고 기존 브래킷의 진동 허용치가 부족하기 때문", buy="설비구매팀 윤도현", quote_change="배선 18m 연장과 방진 브래킷 제작, 이틀 시운전 인력", quote="106,000,000원", quote_qty="구동부 4세트", quote_schedule="2026년 9월 17~18일", adjust="안전에 필요한 브래킷과 펜스는 유지하고 선택형 원격진단 옵션은 제외", final_vendor="한빛모션", final_location="동부허브 1층 자동분류 3번 라인 서측 점검구", ar_note="연초 투자계획에서 100,000,000원이 승인됐으나 최신 견적은 6% 증가", finance_request="증가한 6,000,000원의 추가 예산 사용 승인"),
    dict(project="서부센터 포장필름 안전재고 구매", request="서부센터 자재운영팀 배지우", vendor="새봄패키징", initial="72,000,000원", initial_qty="포장필름 12,000롤", scope="성수기 8주분 안전재고 확보", location="서부센터 자재창고 A구역", schedule="2026년 9월 1일", reason="납기 지연 시 출고 포장 라인이 중단될 가능성", cost="서부센터 포장재 비용센터", review="시설팀은 적재 위치와 소방 통로를, 구매팀은 MOQ와 복수 견적을 확인해 주시기 바랍니다.", safety="시설안전팀 문서아", safety_change="A구역 단일 적재에서 A·C구역 분산 적재로 바꾸고 팔레트 간격을 1.2m로 확보", safety_reason="15,000롤을 한 구역에 두면 스프링클러 살수 범위와 피난 통로를 침범하기 때문", buy="구매전략팀 고준혁", quote_change="공급업체 MOQ 15,000롤과 10,000롤·5,000롤 분할 납품, 납품별 30일 지급", quote="85,500,000원", quote_qty="포장필름 15,000롤", quote_schedule="2026년 8월 28일 및 9월 10일", adjust="MOQ를 수용하되 두 창고로 분산하고 2회 납품하여 보관 한도를 지키는 안", final_vendor="새봄패키징", final_location="서부센터 자재창고 A구역 및 C구역", ar_note="구매팀의 우선협상 대상 선정은 끝났지만 신규 업체에 대한 재무 검토는 시작 전", finance_request="15,000롤 수량 조정안과 신규 공급업체 사용에 대한 예산 승인"),
    dict(project="중앙공장 비전검사기 증설공사", request="중앙공장 생산혁신팀 차예린", vendor="정밀비전솔루션", initial="450,000,000원", initial_qty="비전검사기 3대와 서버 1식", scope="검사기 설치, 서버 연동과 성능 검증", location="중앙공장 검사동 2·3·4라인", schedule="2026년 11월 20일", reason="수작업 재검사 월 160시간과 생산 전환 지연", cost="중앙공장 자동화 투자 비용센터", review="품질보증팀은 검사 정확도를, 시설팀은 전원과 설치 공간을, 구매팀은 장비 견적을 검토해 주시기 바랍니다.", safety="시설기술팀 신유나", safety_change="3개 라인 동시 설치 대신 2·3라인 우선 설치로 줄이고 분전반 증설 위치를 북측 벽면으로 변경", safety_reason="4라인 통로 폭이 장비 반입 기준에 미달하고 생산 중단 시간을 14시간 이내로 제한해야 하기 때문", buy="자동화구매팀 장해원", quote_change="장비 2대에 고해상도 카메라와 검증 소프트웨어를 추가하고 서버는 기존 장비를 활용", quote="430,000,000원", quote_qty="비전검사기 2대", quote_schedule="2026년 11월 8~9일", adjust="1차 공사는 2·3라인만 진행하고 4라인은 효과 확인 후 별도 검토하는 단계안", final_vendor="정밀비전솔루션", final_location="중앙공장 검사동 2·3라인 및 북측 분전반", ar_note="자동화 예산은 예약됐지만 투자위원회 심의와 구매 예산 승인은 아직 요청 전", finance_request="430,000,000원 예산 사용 가능 여부와 투자심의 상신 전 재무 의견"),
    dict(project="북부물류 재고시스템 및 스캐너 교체공사", request="북부물류 IT운영팀 류민재", vendor="로지웍스", initial="200,000,000원", initial_qty="소프트웨어 라이선스 1식", scope="재고시스템 소프트웨어 고도화와 원격 적용", location="북부물류 전산실", schedule="2026년 10월 4일", reason="재고 동기화 지연으로 하루 70건의 수기 확인 발생", cost="북부물류 정보화 투자 비용센터", review="정보보안팀은 전환 방식을, 현장운영팀은 업무 중단 시간을, 구매팀은 라이선스 범위를 검토해 주시기 바랍니다.", safety="현장시설팀 진소희", safety_change="전산실 작업에 더해 입고구역 2곳의 스캐너 교체 구역을 펜스로 분리하고 전환을 주말로 변경", safety_reason="기존 스캐너 12대가 새 암호화 규격을 지원하지 않고 영업시간 작업 시 입고 동선과 겹치기 때문", buy="디지털구매팀 조아인", quote_change="스캐너 12대, 현장 배선과 설치 인력을 소프트웨어 범위에 추가", quote="202,000,000원", quote_qty="소프트웨어 1식과 스캐너 12대", quote_schedule="2026년 10월 11일", adjust="기존 소프트웨어 전환안에 필수 스캐너만 포함하고 예비 단말 3대는 제외", final_vendor="로지웍스", final_location="북부물류 전산실과 입고구역 1·2번", ar_note="소프트웨어 단독 투자계획 승인은 있었지만 물리 장비가 포함된 현재 범위는 예산 검토 전", finance_request="장비가 추가된 202,000,000원 변경 범위에 대한 예산 승인"),
    dict(project="남부센터 냉각펌프 교체공사", request="남부센터 시설팀 임다온", vendor="푸른기계설비", initial="64,000,000원", initial_qty="냉각펌프 2대", scope="펌프 교체와 하루 시운전", location="남부센터 기계실 동측", schedule="2026년 10월 18일", reason="진동 수치 상승으로 냉장 구역 가동률 저하 위험", cost="남부센터 유지보수 비용센터", review="안전환경팀은 차단과 양중 방식을, 운영팀은 냉장 구역 영향 시간을, 구매팀은 교체 견적을 검토해 주시기 바랍니다.", safety="안전환경팀 백은찬", safety_change="두 대 동시 정지를 한 대씩 순차 교체로 바꾸고 임시 바이패스 호스와 밀폐공간 감시자를 추가", safety_reason="동시 정지 시 냉장 구역 온도를 유지할 수 없고 양중 장비 회전 반경이 작업자 통로와 겹치기 때문", buy="시설구매팀 강재희", quote_change="예비펌프 1대와 임시 호스, 이틀 설치 인력을 추가", quote="78,000,000원", quote_qty="냉각펌프 3대와 임시 호스 1세트", quote_schedule="2026년 10월 19~20일", adjust="안전 항목은 유지하고 도장 보수는 제외하며 예비펌프 1대는 고장 대응용으로 포함", final_vendor="푸른기계설비", final_location="남부센터 기계실 동측 펌프실", ar_note="업체 현장 미팅과 작업 슬롯 확보는 끝났지만 예산 승인이나 공사 지시는 하지 않음", finance_request="78,000,000원 변경 견적 기준의 예산 승인"),
    dict(project="연구동 분석장비 연산모듈 설치공사", request="연구지원팀 송라온", vendor="데이터코어", initial="120,000,000원", initial_qty="연산모듈 4개와 유지보수 2년", scope="모듈 설치, 데이터 연동과 원격지원", location="연구동 3층 분석실", schedule="2026년 9월 30일", reason="야간 분석 대기와 연구 일정 지연", cost="연구장비 개선 비용센터", review="컴플라이언스팀은 데이터 처리 범위를, 법무팀은 지원 조항을, 시설팀은 설치 환경을 확인해 주시기 바랍니다.", safety="컴플라이언스팀 민정우", safety_change="해외 원격지원을 국내 로그 한정 지원으로 바꾸고 장비 데이터망과 사무망을 물리적으로 분리", safety_reason="연구 데이터가 원격지원 과정에서 노출될 수 있고 기존 포트가 공용망에 연결돼 있기 때문", buy="연구구매팀 이도경", quote_change="유지보수를 3년으로 늘리고 국내 지원 인력과 망분리 배선을 추가", quote="128,000,000원", quote_qty="연산모듈 4개와 유지보수 3년", quote_schedule="2026년 10월 7일", adjust="법무·컴플라이언스 요구 조건은 유지하고 성능 리포트 옵션만 제외", final_vendor="데이터코어", final_location="연구동 3층 분석실 및 전산실 전용 포트", ar_note="법무와 컴플라이언스 문안 검토는 끝났으나 구매 예산 검토와 Ariba 절차는 시작 전", finance_request="128,000,000원 예산 승인과 PR 상신 가능 여부 확인"),
    dict(project="고객상담 분석서비스 도입", request="고객경험팀 나서윤", vendor="별빛데이터", initial="54,000,000원", initial_qty="상담 데이터 20,000건", scope="3개월 분석서비스와 결과 리포트", location="본사 고객경험팀 국내 클라우드 영역", schedule="2026년 9월 5일", reason="재문의 원인 분석과 상담 품질 개선 필요", cost="고객경험 서비스 비용센터", review="법무팀은 데이터 처리 조항을, 정보보안팀은 저장 위치를, 구매팀은 서비스 견적을 확인해 주시기 바랍니다.", safety="법무팀 김하람", safety_change="공급업체 변경 검토에 따라 재위탁사 실사와 종료 후 삭제증명 조항을 새로 확인", safety_reason="기존 검토는 별빛데이터와 재위탁 금지 조건에 한정돼 대체 업체 조건에 그대로 적용할 수 없기 때문", buy="서비스구매팀 전우진", quote_change="푸른인사이트 기준 데이터 25,000건, 검수 후 일괄 지급과 9월 12일 시작 조건", quote="57,000,000원", quote_qty="상담 데이터 25,000건", quote_schedule="2026년 9월 12일", adjust="납기 대응을 위해 대체 업체를 검토하되 재위탁사 자료 확인 전에는 업체를 확정하지 않는 안", final_vendor="푸른인사이트(검토안)", final_location="본사 고객경험팀 국내 클라우드 전용 영역", ar_note="기존 업체 법무 검토는 완료됐지만 공급업체와 계약 조건 변경으로 새 검토가 필요", finance_request="57,000,000원 변경안의 예산 영향과 대체 업체 진행 가능 여부 검토"),
    dict(project="온라인 추천엔진 전체 적용", request="온라인사업팀 도유진", vendor="넥스트추천", initial="30,000,000원", initial_qty="방문자 10% 대상 6주 시범", scope="추천엔진 시범 운영과 효과 측정", location="온라인몰 시범 트래픽 영역", schedule="2026년 9월 1일", reason="추천 정확도와 전환율 개선 가능성 검증", cost="온라인사업 실험 비용센터", review="정보보안팀은 데이터 범위를, 플랫폼팀은 연동 일정을, 구매팀은 시범 계약을 검토해 주시기 바랍니다.", safety="정보보안팀 우지안", safety_change="시범 트래픽을 15%로 조정하고 보관 기간을 90일에서 45일로 단축", safety_reason="표본 신뢰도를 확보하면서도 개인 식별정보 노출과 장기 보관 위험을 낮추기 위해서", buy="플랫폼구매팀 허정민", quote_change="시범 결과를 반영한 전체 트래픽 12개월 사용료와 별도 운영지원", quote="240,000,000원", quote_qty="전체 트래픽 대상 12개월", quote_schedule="2026년 10월 15일", adjust="시범 성공 결과는 근거 자료로 사용하되 전체 적용은 별도 구매안으로 준비", final_vendor="넥스트추천", final_location="온라인몰 전체 트래픽 운영 영역", ar_note="시범 운영 예산은 승인됐지만 전체 적용에 대한 재무 승인과 Ariba PR은 별도", finance_request="240,000,000원 전체 적용 예산의 사용 가능 여부 확인"),
    dict(project="동남권 긴급운송 용역 갱신", request="동남권 물류기획팀 이가온", vendor="다온트랜스", initial="월 48,000,000원", initial_qty="긴급운송 차량 8대", scope="6개월 운송용역과 야간 배차 2회", location="동남권 허브 상차장 1·2구역", schedule="2026년 9월 1일", reason="계약 공백 시 당일 출고 대응률 하락", cost="동남권 운송비 비용센터", review="안전환경팀은 상차 동선을, 법무팀은 책임 한도와 보험을, 구매팀은 갱신 단가를 검토해 주시기 바랍니다.", safety="허브안전팀 정루리", safety_change="차량 대기 위치를 1구역 앞에서 외곽 대기장으로 옮기고 야간 유도 인력 2명을 추가", safety_reason="피크 시간에 대기 차량이 비상차로를 막고 지게차 회전 구간과 겹치기 때문", buy="운송구매팀 박시안", quote_change="차량 10대, 야간 배차 3회, 분기별 유류 할증과 9월 3일 시작 조건", quote="월 52,000,000원", quote_qty="긴급운송 차량 10대", quote_schedule="2026년 9월 3일", adjust="차량 10대는 유지하되 주간 예비 운행 1회는 제외하고 야간 유도 인력을 포함", final_vendor="다온트랜스", final_location="동남권 허브 외곽 대기장과 상차장 1·2구역", ar_note="계약 문안과 보험 조건은 검토했지만 서명 요청, 발주서와 계약 체결은 모두 PR 이후 진행 예정", finance_request="월 52,000,000원 용역 예산 승인과 PR 상신 가능 여부 확인"),
    dict(project="제2공장 가스감지기 교체공사", request="제2공장 안전운영팀 구서진", vendor="새길센서", initial="96,000,000원", initial_qty="가스감지기 12대와 통합패널 1식", scope="감지기 교체, 통합경보 연동과 시운전", location="제2공장 혼합동 출입구 및 공정실", schedule="2026년 9월 15일", reason="자가진단 오류 반복으로 작업구역 안전 확보가 시급", cost="제2공장 안전설비 비용센터", review="안전환경팀은 감지 위치를, 시설팀은 전원 차단 일정을, 구매팀은 긴급 납기 견적을 검토해 주시기 바랍니다.", safety="공장안전환경팀 권태린", safety_change="출입구 인접 2대를 서측 벽면으로 옮기고 패널을 2식으로 분리하며 안전펜스를 추가", safety_reason="출입문 개방 바람이 측정값에 영향을 주고 단일 패널 고장 시 전체 구역 경보가 중단될 수 있기 때문", buy="긴급구매팀 안지후", quote_change="감지기 10대, 패널 2식, 긴급 운송과 주말 설치 인력", quote="98,000,000원", quote_qty="가스감지기 10대와 통합패널 2식", quote_schedule="2026년 9월 22일", adjust="임대 감지기 2대는 임시 안전조치로 유지하고 본 구매는 필수 감지기 10대와 패널 2식만 반영", final_vendor="새길센서", final_location="제2공장 혼합동 서측 벽면 및 공정실 2개 구역", ar_note="임시 임대 사용은 허용됐지만 본 구매 예산 승인, Ariba PR과 공사 착수는 아직", finance_request="긴급 본 구매 98,000,000원에 대한 재무 검토와 예산 승인"),
]


def signature(display: str) -> str:
    return display.split()[-1]


def bodies(s: dict, index: int) -> list[str]:
    requester = signature(s["request"])
    safety = signature(s["safety"])
    buyer = signature(s["buy"])
    first_closes = [
        "검토 의견을 모아 수정안을 정리한 뒤 김재무님께 예산 승인을 요청하고 Ariba PR을 준비하겠습니다.",
        "유관부서 회신을 반영해 김재무님과 예산을 확인한 다음에만 Ariba PR 상신을 진행하겠습니다.",
        "사전 검토가 끝나면 변경 견적을 기준으로 김재무님께 승인 요청을 드리고 PR을 작성하겠습니다.",
    ]
    b1 = f"""안녕하세요, {s['request']}입니다.

아래와 같이 {s['project']}을 진행하고자 하여 사전 검토 요청드립니다.

- 공사명: {s['project']}
- 공사업체: {s['vendor']}
- 공사금액: {s['initial']}
- 공사내용: {s['scope']}
- 공사위치: {s['location']}
- 공사 예정일: {s['schedule']}
- 요청 사유: {s['reason']}
- 예산 항목 또는 비용센터: {s['cost']}
- 첨부자료: 업체 견적서, 작업계획서(메일 기재용이며 실제 파일 없음)

{s['review']} 재무팀 김재무님께서는 유관부서 의견이 정리된 뒤 PR 상신 전 예산을 검토해 주시면 감사하겠습니다.

{first_closes[index % len(first_closes)]}

감사합니다.
{requester} 드림."""
    b2 = f"""안녕하세요, {s['safety']}입니다.

요청하신 {s['project']}의 위치와 작업 방법을 현장 동선 기준으로 검토했습니다. 현재 계획대로 진행하면 {s['safety_reason']} 조건 조정이 필요합니다.

- 위치·작업 변경: {s['safety_change']}
- 추가 확인: 작업 전 위험성 평가, 출입 통제와 담당자 안전교육
- 일정 의견: 운영부서와 작업 가능 시간을 다시 맞춘 뒤 확정

위 조건을 반영하면 안전 측 사전 의견을 마무리할 수 있습니다. 다만 이 회신은 작업 방법에 관한 검토이며 예산 사용이나 업체 발주를 승인하는 내용은 아닙니다.

변경 위치와 범위로 재견적을 받아 다시 공유해 주시기 바랍니다.

감사합니다.
{safety} 드림."""
    b3 = f"""안녕하세요, {s['buy']}입니다.

안전·시설 의견을 반영한 조건으로 {s['vendor']}에 재견적과 납기를 확인했습니다. 위치와 작업 범위가 달라져 최초 견적에서 다음 항목이 변경됐습니다.

- 변경 견적: {s['quote']}
- 변경 수량: {s['quote_qty']}
- 추가·변경 범위: {s['quote_change']}
- 업체 가능 일정: {s['quote_schedule']}

업체는 위 조건으로 견적서를 다시 발행할 수 있다고 회신했으나 아직 발주서나 계약서는 작성하지 않았습니다. 요청 부서에서는 필수 항목과 제외 가능한 항목을 구분해 최종 조정안을 알려주시기 바랍니다.

김재무님 예산 검토에 사용할 비교 내역은 함께 정리하겠습니다.

감사합니다.
{buyer} 드림."""
    b4 = f"""안녕하세요, {s['request']}입니다.

안전·시설 검토와 구매팀 재견적을 반영한 조정안을 공유드립니다. 운영 영향과 비용을 함께 검토해 {s['adjust']}으로 범위를 정리했습니다.

- 조정 수량: {s['quote_qty']}
- 조정 금액: {s['quote']}
- 작업 위치: {s['final_location']}
- 예정 일정: {s['quote_schedule']}
- 업체: {s['final_vendor']}

{s['ar_note']} 유관부서가 제시한 기술 조건은 반영했지만 Ariba PR 생성, 구매 승인, 발주서 발행, 계약 체결과 현장 착수는 진행하지 않았습니다.

위 조정안에 빠진 사항이 있는지 확인 부탁드리며, 회신을 받으면 김재무님께 예산 승인을 요청하겠습니다.

감사합니다.
{requester} 드림."""
    b5 = f"""안녕하세요, 김재무님.

{s['request']} {requester}입니다. 유관부서 의견과 변경 견적을 반영한 {s['project']} 최종 조정안을 기준으로 PR 상신 전 예산 검토를 요청드립니다.

- 최종 공사·구매명: {s['project']}
- 최종 업체: {s['final_vendor']}
- 최신 금액: {s['quote']}
- 최신 수량: {s['quote_qty']}
- 최종 위치: {s['final_location']}
- 예정 일정: {s['quote_schedule']}
- 최초 대비 변경: {s['initial_qty']}·{s['initial']}에서 현재 수량·금액 및 작업 조건으로 조정
- 유관부서 의견: {s['safety_change']} 조건을 반영했고 구매팀이 재견적과 납기를 확인

현재 업체 견적과 작업 조건까지만 정리됐으며 Ariba PR, 구매 승인, 발주서, 계약과 실제 작업은 시작하지 않았습니다. 김재무님께 {s['finance_request']}을 요청드립니다.

승인해 주시면 회신 내용을 근거로 Ariba PR을 상신하겠습니다. 추가 자료가 필요하면 말씀 부탁드립니다.

감사합니다.
{requester} 드림."""
    return [b1, b2, b3, b4, b5]


def main() -> None:
    records = json.loads(TARGET.read_text())
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["thread_id"], []).append(record)
    replacements: list[tuple[str, str]] = []
    for index, thread_id in enumerate(sorted(grouped)):
        generated = bodies(SCENARIOS[index], index)
        for record, body in zip(grouped[thread_id], generated, strict=True):
            replacements.append((record["body"], body))
    print("*** Begin Patch")
    print(f"*** Update File: {TARGET.resolve()}")
    for old, new in replacements:
        print("@@")
        print(f"-    \"body\": {json.dumps(old, ensure_ascii=False)}")
        print(f"+    \"body\": {json.dumps(new, ensure_ascii=False)}")
    print("*** End Patch")


if __name__ == "__main__":
    main()
