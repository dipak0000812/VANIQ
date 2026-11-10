# Known limitations

* No native Ahirani STT support is claimed or established for Gnani Prisma. Pilot results used Marathi (`mr-IN`) and `indic-auto`.
* No accuracy numbers for Ahirani exist in this repository. Demo-mode numbers are synthetic.
* Correction is a lexicon lookup with neighbouring-word context; it is not machine learning and contains no linguistic data of its own.
* No dialect identification. STT language codes are language detection.
* Energy-based segmentation is not speech-specific, and default thresholds need calibration per microphone/room.
* Reviewer identity is self-declared; there is no authentication or access control. Do not expose the server publicly.
* Single local SQLite connection: fine for one user, not for concurrent teams.
* Only the Gnani provider is implemented (the abstraction supports more).
* Browser recording depends on browser MediaRecorder support and microphone permission.
* The UI was exercised programmatically (jsdom against the live server), not manually in real browsers.
* Evaluation results from a handful of clips are anecdotal.
