#define TEMP_DEFAULT 25
#define TEMP_LIMIT 80
#define SOURCE_OFFSET 3
#define UNUSED_LIMIT 999

static int source_value = 10;
static int a = TEMP_DEFAULT;
static int unrelated_global = 123;
int g_temperature = TEMP_DEFAULT;

static int adjust_value(int value)
{
    return value + SOURCE_OFFSET;
}

static void unrelated_function(void)
{
    unrelated_global = UNUSED_LIMIT;
}

void update_a(void)
{
    a = adjust_value(source_value);
}

void check_a(void)
{
    if (a >= TEMP_LIMIT) {
        a = TEMP_LIMIT;
    }
}

void update_temperature(void)
{
    g_temperature = a;
}

int get_temperature(void)
{
    return g_temperature;
}
