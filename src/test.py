from datetime import datetime, timedelta, timezone
past = datetime.now(timezone.utc) + timedelta(days=1)
present = datetime.now(timezone.utc)
print(past > present)

print(datetime.fromtimestamp(1748701883, timezone.utc))