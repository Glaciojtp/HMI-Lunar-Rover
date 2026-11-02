#pragma once
enum { ESP_RST_POWERON = 1, ESP_RST_BROWNOUT = 9 };
extern int g_causa_reset;
inline int esp_reset_reason() { return g_causa_reset; }
