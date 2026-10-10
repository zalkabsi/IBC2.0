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

import javax.swing.JCheckBox;
import javax.swing.JDialog;

class ConfigureAllowLocalhostOnlyTask implements ConfigurationAction {

    private final boolean localhostOnly;
    private JDialog configDialog;

    ConfigureAllowLocalhostOnlyTask(boolean localhostOnly) {
        this.localhostOnly = localhostOnly;
    }

    @Override
    public void run() {
        try {
            Utils.logToConsole("Setting AllowLocalhostOnly");

            Utils.selectApiSettings(configDialog);

            JCheckBox cb = SwingUtils.findCheckBox(configDialog, "Allow connections from localhost only");
            if (cb == null) {
                Utils.logError("could not find the 'Allow connections from localhost only' checkbox");
                return;
            }

            if (cb.isSelected() == localhostOnly) {
                Utils.logToConsole("'Allow connections from localhost only' is already set to: " + localhostOnly);
                return;
            }

            if (!SessionManager.isGateway()) {
                JCheckBox api = SwingUtils.findCheckBox(configDialog, "Enable ActiveX and Socket Clients");
                if (api != null && api.isSelected()) ConfigDialogManager.configDialogManager().setApiConfigChangeConfirmationExpected();
            }
            cb.setSelected(localhostOnly);
            Utils.logToConsole("'Allow connections from localhost only' is now set to: " + localhostOnly);
        } catch (IbcException e) {
            Utils.logException(e);
        }
    }

    @Override
    public void initialise(JDialog configDialog) {
        this.configDialog = configDialog;
    }
}
