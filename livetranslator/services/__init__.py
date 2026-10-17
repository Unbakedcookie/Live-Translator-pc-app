"""Services: audio, ASR, MT, OCR, hotkeys, models, metrics, speakers (spec §6.1).

Services never touch widgets. They report to the store with `dispatch` from their own threads.
"""
