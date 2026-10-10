// This file is part of IBC.
// For conditions of distribution and use, see copyright notice in COPYING.txt

// IBC is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// IBC is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with IBC.  If not, see <http://www.gnu.org/licenses/>.

package ibcalpha.ibc;

import java.awt.Window;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

/**
 * User-editable rules for dialogs that no built-in handler recognises, loaded
 * from the file named by the DialogRulesFile setting. Each non-comment line is
 * of the form:
 *
 *   title=&lt;regex&gt; ; text=&lt;regex&gt; ; click=&lt;button text&gt;
 *
 * 'title' and 'text' are case-insensitive regular expressions that must match
 * somewhere in the window title / window text ('text' is optional); 'click' is
 * the exact text of the button to press. Because rules only ever apply to
 * windows that IBC does not otherwise recognise, and only fire when a rule
 * explicitly matches, nothing is ever clicked without the user asking for it.
 */
class DialogRules {
    static final class Rule {
        final Pattern title;
        final Pattern text;
        final String click;

        Rule(Pattern title, Pattern text, String click) {
            this.title = title;
            this.text = text;
            this.click = click;
        }

        boolean matches(String windowTitle, String windowText) {
            return title.matcher(windowTitle).find()
                    && (text == null || text.matcher(windowText).find());
        }
    }

    private final List<Rule> rules;

    DialogRules(List<Rule> rules) {
        this.rules = rules;
    }

    private static DialogRules instance;

    static synchronized DialogRules instance() {
        if (instance == null) {
            String path = Settings.settings().getString("DialogRulesFile", "");
            if (path.isEmpty()) {
                instance = new DialogRules(new ArrayList<>());
            } else {
                try {
                    List<String> lines = Files.readAllLines(Paths.get(path), StandardCharsets.UTF_8);
                    instance = parse(lines);
                    Utils.logToConsole("Loaded " + instance.rules.size() + " dialog rule(s) from " + path);
                } catch (IOException e) {
                    Utils.logError("could not read DialogRulesFile '" + path + "': " + e.getMessage());
                    instance = new DialogRules(new ArrayList<>());
                }
            }
        }
        return instance;
    }

    static DialogRules parse(List<String> lines) {
        List<Rule> rules = new ArrayList<>();
        int lineNo = 0;
        for (String raw : lines) {
            lineNo++;
            String line = raw.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            Pattern title = null;
            Pattern text = null;
            String click = null;
            try {
                for (String part : line.split(";")) {
                    int eq = part.indexOf('=');
                    if (eq < 0) throw new IllegalArgumentException("missing '='");
                    String key = part.substring(0, eq).trim().toLowerCase();
                    String value = part.substring(eq + 1).trim();
                    switch (key) {
                        case "title": title = Pattern.compile(value, Pattern.CASE_INSENSITIVE); break;
                        case "text": text = Pattern.compile(value, Pattern.CASE_INSENSITIVE | Pattern.DOTALL); break;
                        case "click": click = value; break;
                        default: throw new IllegalArgumentException("unknown key '" + key + "'");
                    }
                }
                if (title == null || click == null || click.isEmpty()) {
                    throw new IllegalArgumentException("'title' and 'click' are required");
                }
                rules.add(new Rule(title, text, click));
            } catch (IllegalArgumentException e) {
                Utils.logError("ignoring invalid dialog rule at line " + lineNo + ": " + e.getMessage());
            }
        }
        return new DialogRules(rules);
    }

    Rule find(String windowTitle, String windowText) {
        for (Rule r : rules) {
            if (r.matches(windowTitle, windowText)) return r;
        }
        return null;
    }

    int size() {
        return rules.size();
    }

    /**
     * Called for a window that no handler recognised. Returns true if a rule
     * matched and its button was clicked.
     */
    static boolean tryApply(Window window) {
        String title = SwingUtils.getWindowTitle(window);
        String text = SwingUtils.getTexts(window);
        Rule rule = instance().find(title, text);
        if (rule == null) return false;
        if (SwingUtils.clickButton(window, rule.click)) {
            Utils.logToConsole("Dialog rule applied to '" + title + "': clicked '" + rule.click + "'");
            Events.emit(Events.RULE_APPLIED, title + " -> " + rule.click);
            return true;
        }
        Utils.logError("dialog rule matched '" + title + "' but button '" + rule.click + "' was not found");
        return false;
    }
}
