#define TEMP_LIMIT 80

#pragma section DATA="RAM"
static int g_temperature = 20;

void update_temperature(void)
{
    g_temperature += 1;
}

void check_temperature(void)
{
    if (g_temperature >= TEMP_LIMIT) {
        g_temperature = TEMP_LIMIT;
    }
}
