package ibcalpha.ibc;

import java.time.LocalTime;
import java.util.Arrays;

/**
 * Dependency-free tests for the pure-logic parts of IBC. Run with 'ant test'.
 * Exits non-zero if any check fails.
 */
public class CoreTests {
    private static int failures = 0;
    private static int checks = 0;

    private static void check(boolean condition, String what) {
        checks++;
        if (!condition) {
            failures++;
            System.err.println("FAIL: " + what);
        }
    }

    public static void main(String[] args) {
        parseTimeAcceptsCommonForms();
        parseTimeRejectsGarbage();
        eventsEscapeProducesValidJsonStrings();
        dialogRulesParseAndMatch();
        dialogRulesIgnoreInvalidLines();

        System.out.println(checks + " checks, " + failures + " failures");
        if (failures > 0) System.exit(1);
    }

    static void parseTimeAcceptsCommonForms() {
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime("02:00 PM").equals(LocalTime.of(14, 0)), "02:00 PM");
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime("2:00 PM").equals(LocalTime.of(14, 0)), "2:00 PM (single-digit hour, issue #364)");
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime("2:00 pm").equals(LocalTime.of(14, 0)), "2:00 pm lower case");
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime("  11:45   PM ").equals(LocalTime.of(23, 45)), "extra whitespace");
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime("12:30 AM").equals(LocalTime.of(0, 30)), "12:30 AM");
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime("14:00").equals(LocalTime.of(14, 0)), "24-hour 14:00");
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime("2:00PM").equals(LocalTime.of(14, 0)), "2:00PM no space");
    }

    static void parseTimeRejectsGarbage() {
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime("") == null, "empty");
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime(null) == null, "null");
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime("25:00") == null, "25:00");
        check(ConfigureAutoLogoffOrRestartTimeTask.parseTime("noon") == null, "noon");
    }

    static void eventsEscapeProducesValidJsonStrings() {
        check(Events.escape("a\"b").equals("a\\\"b"), "quote escaped");
        check(Events.escape("a\\b").equals("a\\\\b"), "backslash escaped");
        check(Events.escape("a\nb\tc").equals("a\\nb\\tc"), "control chars escaped");
        check(Events.escape("\u0001").equals("\\u0001"), "low control char escaped");
        check(Events.escape(null).equals(""), "null -> empty");
    }

    static void dialogRulesParseAndMatch() {
        DialogRules rules = DialogRules.parse(Arrays.asList(
                "# comment",
                "",
                "title=^Gateway$ ; text=prediction markets ; click=Close",
                "title=Tip of the day ; click=Close"));
        check(rules.size() == 2, "two rules parsed");
        DialogRules.Rule r = rules.find("Gateway", "Trade Prediction Markets today");
        check(r != null && r.click.equals("Close"), "title+text rule matches");
        check(rules.find("Gateway", "something else") == null, "text must also match");
        check(rules.find("Order confirmation", "Close") == null, "unrelated dialog is not matched");
        check(rules.find("tip of the day", "") != null, "title match is case-insensitive");
    }

    static void dialogRulesIgnoreInvalidLines() {
        DialogRules rules = DialogRules.parse(Arrays.asList(
                "title=[unclosed ; click=OK",
                "click=OK",
                "title=x",
                "nonsense",
                "bogus=1 ; title=x ; click=OK",
                "title=ok ; click=Close"));
        check(rules.size() == 1, "only the valid rule survives, got " + rules.size());
    }
}
