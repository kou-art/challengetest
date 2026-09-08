typedef struct
{
    int status;
    int value;
} DeviceA;

typedef struct
{
    int status;
    int value;
} DeviceB;

DeviceA g_device_a = {0, 10};
DeviceB g_device_b = {0, 20};

int g_target = 0;

void update_target(void)
{
    g_target = g_device_a.status + g_device_b.status;
}
