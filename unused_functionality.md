# Unused Legacy Functionality Reference

This document captures the legacy implementations and details for features that have not been ported to the FastAPI stack, preserving them for future reference.

---

## 1. Reading Lists & Device Syncing (Legacy `readinglist.py`)

### Overview
In the legacy codebase ([readinglist.py](file:///e:/Coding%20Projects/mylar3/.old/mylar/readinglist.py)), Mylar tracked custom reading lists or story arcs and synced downloaded comic books directly to reading devices (like tablets or external servers) using FTP or SFTP.

### Key Logic & Mechanics
1. **Database Tables**:
   - `readlist`: Tracked individual issues on the user's reading list. Fields:
     - `IssueID`, `ComicID`, `ComicName`, `Issue_Number`, `IssueDate`, `SeriesYear`, `Location` (path on disk), `Status` (`Added`, `Read`, `Downloaded`), `DateAdded`, `StatusChange`.
   - `readinglist`: Tracked the larger story arc / reading list metadata.
2. **Operations**:
   - `addtoreadlist`: Added target `IssueID` (or `AnnualID`) from the watchlist to the reading list.
   - `markasRead`: Toggled status of issues/story arcs between `Added` and `Read`.
   - `syncreading`: Found all issues with `Status = 'Added'`, verified files existed, pinged the tablet hostname, and called a file transmitter wrapper `mylar.ftpsshup.sendfiles(sendlist)` to upload the files. On successful upload, marked status as `Downloaded`.
3. **Configuration Options**:
   - `tab_host`: IP / hostname of the reading device (e.g., tablet).
   - `tab_pass`, `tab_user`: FTP/SFTP credentials.

---

## 2. CBR to CBZ Archive Conversion

### Overview
Comics are archived in either `.cbr` (RAR format) or `.cbz` (ZIP format). Many reading applications and metadata taggers (like ComicTagger) only support CBZ natively. In the legacy codebase, Mylar automatically converted CBR archives to CBZ format during post-processing.

### Current Implementation Stub
In the new codebase, a placeholder exists within [PostProcessorService.convert_cbr_to_cbz](file:///e:/Coding%20Projects/mylar3/app/services/post_processor.py#L219):
```python
async def convert_cbr_to_cbz(self, cbr_path: str) -> str:
    logger.warning(f"[PostProcessor] CBR to CBZ conversion requested for {cbr_path} but alpine container lacks unrar. Skipping conversion.")
    raise NotImplementedError("CBR to CBZ requires system unrar/patool libraries.")
```

### Required Implementation Steps
If porting this functionality in the future:
1. **Container Package Dependencies**:
   - Ensure the system has `unrar` / `extract` installed (requires non-free repository/packages on Alpine or Debian in `Dockerfile.dev`).
   - Install a python library such as `patool` or use standard subprocess calling `unrar` and `zip`.
2. **Logic Sequence**:
   - Create a temporary directory.
   - Extract all image files from the source `.cbr` file to the temporary directory.
   - Walk the temporary directory and create a new `.cbz` (ZIP format) archive containing those images.
   - Ensure permissions are preserved, clean up the temporary extraction directory, and delete the original `.cbr` file.
   - Update the file reference to use the newly created `.cbz` path.
