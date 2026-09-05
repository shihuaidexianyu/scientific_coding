# Synthetic epoch study

This is a small standard-library example, not the user's original cluster code.
Run `python analysis.py`. Input values are microvolts, axes are trial/channel/time,
and time values are seconds. Preserve the method and public function signatures.

Each trial/channel subtracts its baseline-sample mean. Average corrected trials
within each condition, subtract control from treatment, and find each channel's
largest absolute difference. Retain its signed amplitude and earliest time on a tie.
The two groups can have different trial counts. Output both summary.json and
corrected_epochs.json under results/ and preserve the original input/config values.
