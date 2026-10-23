#!/bin/bash
CONTAINER_NAME="hermes-litellm"
LIMIT_MB=4096
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    exit 0
fi
USAGE_STR=$(docker stats --no-stream --format "{{.MemUsage}}" "$CONTAINER_NAME" | awk '{print $1}')
NUM=$(echo "$USAGE_STR" | sed 's/[^0-9.]//g')
UNIT=$(echo "$USAGE_STR" | sed 's/[0-9.]//g')
USAGE_MB=$(awk -v num="$NUM" -v unit="$UNIT" 'BEGIN {
    if (unit == "GiB" || unit == "GB") { print num * 1024 }
    else if (unit == "KiB" || unit == "KB") { print num / 1024 }
    else { print num }
}')
IS_OVER=$(awk -v usage="$USAGE_MB" -v limit="$LIMIT_MB" 'BEGIN { print (usage > limit) ? 1 : 0 }')
if [ "$IS_OVER" -eq 1 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [WARNING] $CONTAINER_NAME exceeded RAM limit (${USAGE_MB}MB > ${LIMIT_MB}MB). Force-Restarting..." >> /var/log/hermes_ram_enforcer.log
    docker restart "$CONTAINER_NAME"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [ACTION] $CONTAINER_NAME restarted successfully." >> /var/log/hermes_ram_enforcer.log
fi
