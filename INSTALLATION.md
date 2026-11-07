# Install and play

1. Extract the entire **FIFA16_CareerStats_User_Release.zip** to a folder of your choice.
2. Double-click **CareerStats.exe**.
3. If prompted, use **Locate FIFA 16** or **Locate Profile** to select the correct folders.
4. When the launcher says **Ready to launch**, click **Launch FIFA 16**.

Requires Windows x64 and a FIFA 16 PC installation that matches the [2015/16 profile](profiles/fifa16-2015-16.json). The first launch prepares the two screens automatically. Keep `Data` and `Runtime` beside the executable.

Roster database edits can pass setup. The launcher checks the supported executable and native BIN, the save metadata it uses, and the two Career Mode screen templates. **Historical coverage** describes the records included for matching IDs. It does not affect the technical result.

If FIFA has never created its profile, open FIFA normally once and close it. The launcher checks Windows Documents, including its redirected location, and common OneDrive and custom profile folders. Choose the folder that FIFA actually uses. Selecting it does not move saves or redirect FIFA.

## Close, recover, or remove

Close FIFA normally and wait for the launcher to finish. If the previous session was interrupted, close FIFA and choose **Recover**. If recovery is blocked, keep the journal and use **View Logs**. A setup error identifies the failing native component, save metadata, or screen resources.

The launcher stores its settings, tracking registry, prepared screens and logs in `%LOCALAPPDATA%\FIFA16CareerStats`. Logs can contain paths, save labels and hashes. Redact them before sharing. To uninstall, finish recovery and remove the extracted folder. Keep the local tracking folder if you want to retain your Career history.

Developers should use the separate [build guide](DEVELOPMENT.md).
