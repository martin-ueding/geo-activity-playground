# Sync Between Computers

If you record activities on one device and want to analyze them on multiple computers, you can use a cloud sync service such as Dropbox, Google Drive, or OneDrive. There are two approaches depending on how much isolation you want between machines.

## Approach 1: Sync the Entire Base Directory

The simplest approach is to place the entire base directory inside your sync folder. The program will find everything it needs there, and all data—activities, photos, and the database—stays in one place.

**Constraint:** Only one instance of the program may run at a time across all your machines. SQLite acquires an exclusive lock on the database file during writes. If two machines sync concurrently while the program is open on both, the database can be corrupted. Always close the program on one machine and let the sync complete before opening it on another.

## Approach 2: Sync Only Activities and Photos

If you want each computer to have an independent, fully functional installation—for example, one at home and one on a laptop—you can sync only the raw activity files and photos, and let each machine maintain its own database.

In this setup:

- The `Activities` and `Photos` directories live inside your sync folder.
- Each computer's base directory contains symbolic links pointing to those synced directories.
- Each machine imports the activities independently and builds its own database.

**Caveat:** Changes stored in the database are not synced. This includes explorer cluster names, edited activity metadata, and saved searches. Those live only on the machine where the change was made.

### Creating Symbolic Links

#### Linux and macOS

```bash
ln -s /path/to/your/synced/Activities ~/basedir/Activities
ln -s /path/to/your/synced/Photos ~/basedir/Photos
```

#### Windows (Command Prompt)

```cmd
mklink /J Activities D:\path\to\your\synced\Activities
mklink /J Photos D:\path\to\your\synced\Photos
```

The `/J` flag creates a directory junction, which works without administrator privileges on most systems.

#### Windows (PowerShell)

```powershell
New-Item -ItemType SymbolicLink -Path "C:\basedir\Activities" -Target "D:\path\to\your\synced\Activities"
New-Item -ItemType SymbolicLink -Path "C:\basedir\Photos" -Target "D:\path\to\your\synced\Photos"
```

PowerShell symbolic links may require running PowerShell as Administrator depending on your system's Developer Mode settings.

### After Linking

Once the links are in place, start the program normally and trigger an import. It will read the activity files through the symlinks and populate the local database. Repeat this on each machine.
