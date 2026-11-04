package kr.co.example.hr;

import java.time.Duration;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;

/**
 * 출퇴근 기록을 받아 근무시간을 정규/연장/야간으로 분류한다.
 * 작성자: 인사시스템팀
 */
public class Attendance {

    // 야간근로 시작/종료 시각 (22:00 ~ 06:00)
    private static final LocalTime NIGHT_START = LocalTime.of(22, 0);
    private static final LocalTime NIGHT_END = LocalTime.of(6, 0);
    // 1일 소정근로시간 (분 단위)
    private static final long DAILY_REGULAR_MINUTES = 8 * 60;
    // 휴게시간 4시간당 30분
    private static final long BREAK_PER_FOUR_HOURS = 30;

    private final List<String> warnings = new ArrayList<>();

    /** 하루 근무를 분류한 결과 */
    public static class DayResult {
        public long regularMinutes;
        public long overtimeMinutes;
        public long nightMinutes;

        @Override
        public String toString() {
            return "정규=" + regularMinutes + "분, 연장=" + overtimeMinutes
                    + "분, 야간=" + nightMinutes + "분";
        }
    }

    public DayResult classify(LocalDateTime checkIn, LocalDateTime checkOut) {
        if (!checkOut.isAfter(checkIn)) {
            warnings.add("퇴근 시각이 출근 시각보다 빠름: " + checkIn + " / " + checkOut);
            return new DayResult();
        }
        long total = Duration.between(checkIn, checkOut).toMinutes();
        long breaks = (total / 240) * BREAK_PER_FOUR_HOURS;   // 법정 휴게시간 차감
        long worked = Math.max(0, total - breaks);

        DayResult r = new DayResult();
        r.regularMinutes = Math.min(worked, DAILY_REGULAR_MINUTES);
        r.overtimeMinutes = Math.max(0, worked - DAILY_REGULAR_MINUTES);
        r.nightMinutes = nightOverlap(checkIn, checkOut);
        if (r.overtimeMinutes > 4 * 60) {
            warnings.add("1일 연장근로 4시간 초과: " + checkIn.toLocalDate());
        }
        return r;
    }

    // 야간 구간과 겹치는 분 수를 1분 단위로 센다 (단순하지만 정확함)
    private long nightOverlap(LocalDateTime from, LocalDateTime to) {
        long minutes = 0;
        LocalDateTime cursor = from;
        while (cursor.isBefore(to)) {
            LocalTime t = cursor.toLocalTime();
            if (!t.isBefore(NIGHT_START) || t.isBefore(NIGHT_END)) {
                minutes++;
            }
            cursor = cursor.plusMinutes(1);
        }
        return minutes;
    }

    public long weeklyOvertime(List<DayResult> week) {
        long sum = 0;
        for (DayResult d : week) {
            sum += d.overtimeMinutes;
        }
        if (sum > 12 * 60) {
            warnings.add("주 52시간 초과 (연장 " + sum / 60 + "시간)");
        }
        return sum;
    }

    public List<String> getWarnings() {
        return warnings;
    }

    public static void main(String[] args) {
        Attendance a = new Attendance();
        DayResult d = a.classify(LocalDateTime.of(2026, 3, 2, 9, 0),
                                 LocalDateTime.of(2026, 3, 2, 23, 30));
        System.out.println(d);
        System.out.println(a.getWarnings());
    }
}
