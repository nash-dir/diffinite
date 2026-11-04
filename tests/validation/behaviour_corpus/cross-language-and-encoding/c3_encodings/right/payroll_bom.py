# -*- coding: utf-8 -*-
"""급여 계산 모듈 (월급제/시급제 공통).

근로기준법 기준 연장·야간·휴일 수당을 계산하고 4대보험 공제액을 산출한다.
"""

from dataclasses import dataclass, field

# 4대보험 요율 (근로자 부담분, 예시 값)
NATIONAL_PENSION_RATE = 0.045      # 국민연금
HEALTH_INSURANCE_RATE = 0.03545    # 건강보험
LONG_TERM_CARE_RATIO = 0.1295      # 장기요양 (건강보험료 대비)
EMPLOYMENT_INSURANCE_RATE = 0.009  # 고용보험


@dataclass
class Timesheet:
    """한 달 근무 기록."""
    employee_id: str
    regular_hours: float
    overtime_hours: float = 0.0     # 연장근로
    night_hours: float = 0.0        # 야간근로 (22시~06시)
    holiday_hours: float = 0.0      # 휴일근로
    notes: list = field(default_factory=list)


def hourly_wage(monthly_salary, standard_hours=209):
    """통상시급 = 월 통상임금 / 월 소정근로시간(209시간)."""
    if standard_hours <= 0:
        raise ValueError("소정근로시간은 0보다 커야 합니다")
    return monthly_salary / standard_hours


def premium_pay(sheet, wage):
    """가산수당 계산: 연장·야간·휴일 각각 50% 가산."""
    overtime = sheet.overtime_hours * wage * 1.5
    night = sheet.night_hours * wage * 0.5
    if sheet.holiday_hours <= 8:
        holiday = sheet.holiday_hours * wage * 1.5
    else:
        # 8시간 초과 휴일근로는 100% 가산
        holiday = 8 * wage * 1.5 + (sheet.holiday_hours - 8) * wage * 2.0
    return round(overtime + night + holiday)


def deductions(gross):
    """4대보험 근로자 부담분 공제액."""
    pension = gross * NATIONAL_PENSION_RATE
    health = gross * HEALTH_INSURANCE_RATE
    care = health * LONG_TERM_CARE_RATIO
    employment = gross * EMPLOYMENT_INSURANCE_RATE
    items = {
        "국민연금": int(pension // 10 * 10),
        "건강보험": int(health // 10 * 10),
        "장기요양": int(care // 10 * 10),
        "고용보험": int(employment // 10 * 10),
    }
    items["합계"] = sum(items.values())
    return items


def payslip(sheet, monthly_salary):
    """급여명세서 딕셔너리를 만든다."""
    wage = hourly_wage(monthly_salary)
    extra = premium_pay(sheet, wage)
    gross = monthly_salary + extra
    ded = deductions(gross)
    net = gross - ded["합계"]
    return {
        "사번": sheet.employee_id,
        "기본급": monthly_salary,
        "가산수당": extra,
        "지급총액": gross,
        "공제": ded,
        "실지급액": net,
    }


def format_payslip(slip):
    lines = ["[급여명세서] 사번 %s" % slip["사번"]]
    for key in ("기본급", "가산수당", "지급총액"):
        lines.append("  %-6s %12s원" % (key, format(slip[key], ",")))
    lines.append("  -- 공제 내역 --")
    for key, value in slip["공제"].items():
        lines.append("  %-6s %12s원" % (key, format(value, ",")))
    lines.append("  %-6s %12s원" % ("실지급액", format(slip["실지급액"], ",")))
    return "\n".join(lines)


if __name__ == "__main__":
    ts = Timesheet("K-2031", 209, overtime_hours=12, night_hours=4, holiday_hours=10)
    print(format_payslip(payslip(ts, 3_200_000)))
