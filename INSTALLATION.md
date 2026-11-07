# Install and play

1. Extract the entire **FIFA16_CareerStats_User_Release.zip** to a folder of your choice.
2. Double-click **CareerStats.exe**.
3. If prompted, use **Locate FIFA 16** or **Locate Profile** to select the correct folders.
4. When the launcher says **Ready to launch**, click **Launch FIFA 16**.

Requires Windows x64 and a FIFA 16 PC installation that matches the [2015/16 profile](profiles/fifa16-2015-16.json). The first launch prepares the two screens automatically. Keep `Data` and `Runtime` beside the executable.

Roster database edits can pass setup. The launcher checks the supported executable and native BIN, the save metadata it uses, and the two Career Mode screen templates. **Historical coverage** describes the records included for matching IDs. It does not affect the technical result.

If FIFA has never created its profile, open FIFA normally once and close it. The launcher checks Windows Documents, including its redirected location, and common OneDrive and custom profile folders. Choose the folder that FIFA actually uses. Selecting it does not move saves or redirect FIFA.

## Import an existing Career

1. Close FIFA and choose **Import Existing Career**. Select one or more saves from the detected profile, or use **Browse Folder** or **Add Save Files**.
2. Verify the season, Career date and team ID. For multiple saves, order them oldest first. Select one row at a time to use **Move Up** or **Move Down**, then select the full set again.
3. Use the default choice for a new Career or a selection that already contains registered saves. To append a save manually, choose the exact earlier checkpoint in the parent list. Click **Preview Import** and review the available fields and warnings. Confirm only if the saves belong to the same Career.
4. Click **Launch FIFA 16** and load a registered save. Continue saving normally in FIFA.

**View Linked Saves** lists registered checkpoints and their parents. To add earlier checkpoints before an existing Career, select the earlier files and the first registered save file in chronological order with the default parent choice. The preview identifies this change. To continue a branch, choose the checkpoint you actually loaded.

Career Stats reads selected files and writes its own local registry. FIFA loads saves from its active profile. An external backup can contribute history, but continuing to play that backup requires it to be accessible to FIFA.

## Close, recover, or remove

Close FIFA normally and wait for the launcher to finish. If the previous session was interrupted, close FIFA and choose **Recover**. If recovery is blocked, keep the journal and use **View Logs**. A setup error identifies the failing native component, save metadata, or screen resources.

The launcher stores its settings, tracking registry, prepared screens and logs in `%LOCALAPPDATA%\FIFA16CareerStats`. Logs can contain paths, save labels and hashes. Redact them before sharing. To uninstall, finish recovery and remove the extracted folder. Keep the local tracking folder if you want to retain your Career history.

Developers should use the separate [build guide](DEVELOPMENT.md).
