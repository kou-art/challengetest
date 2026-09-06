// 過熱判定に使用する温度上限
#define TEMP_LIMIT 80

// センサ状態を表す列挙型
typedef enum
{
    SENSOR_OK = 0,
    SENSOR_ERROR = 1
} SensorStatus;

// センサ情報を保持する構造体
typedef struct
{
    int temperature;
    int raw_value;
    SensorStatus status;
} SensorData;

// センサ値を取得する
int read_sensor(void);

// ヒーターを停止する
void heater_off(void);

// 温度値を送信する
void transmit(int value);

// 指定された変数へ値を設定する
void set_value(int *value);

// 現在温度を保持するグローバル変数
int g_temperature = 25;  // 初期温度

/**
 * センサ値を取得し、
 * g_temperatureへ反映する。
 */
void update(void)
{
    // センサから現在値を取得
    g_temperature = read_sensor();
}

/**
 * g_temperatureを上限値と比較し、
 * 必要ならヒーターを停止する。
 */
void control(void)
{
    if (g_temperature >= TEMP_LIMIT) {
        // 過熱条件成立時の処理
        heater_off();
    }
}

// 現在温度を外部へ送信する
void send(void)
{
    transmit(g_temperature);  // 値をそのまま渡す
}

// g_temperatureのアドレスを関数へ渡す
void reset(void)
{
    set_value(&g_temperature);
}

// 現在温度を返す
int get_temperature(void)
{
    return g_temperature;
}

// 現在温度を1増加させる
void increment(void)
{
    g_temperature++;
}
