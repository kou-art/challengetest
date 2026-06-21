using Final.Models;
using Microsoft.Data.SqlClient;
using Dapper;

namespace Final.Repositories;

public class SqlRepository
{
    private readonly IConfiguration _config;
    private readonly string connectionString;
    public SqlRepository(IConfiguration config)
    {
        _config = config;
        connectionString = _config.GetConnectionString("DefaultConnection");
    }

    private List<Shelf> ShelfList;
    private Command RequestCommand;
    private SystemInformation GetResultInfomation;

    public async Task<SystemInformation> SelectInfomationAsync()
    {
        using (var connection = new SqlConnection(connectionString))
        {
            try
            {
                var sql = @"
                                SELECT command_id AS CommandId,
                                command_type AS CommandType,
                                carrier_id AS CarrierId,
                                eqp_name AS EqpName,
                                location AS Location,
                                reception_at AS ReceptionAt,
                                send_at AS SendAt,
                                completion_at AS CompletionAt,
                                command_status AS CommandStatus
                                FROM commands
                                WHERE command_status IN (0,1)
                                UNION ALL
                                SELECT TOP(100) * FROM commands
                                WHERE command_status IN (2,3)
                                ;
                                SELECT shelf_location AS ShelfLocation,
                                stored_carrier_id AS StoredCarrierId,
                                reservation AS Reservation,
                                storage_at AS StorageAt
                                FROM shelves
                                ;";
                using var multi = await connection.QueryMultipleAsync(sql);
                
                var commands = (await multi.ReadAsync<Command>()).ToList();
                var shelves = (await multi.ReadAsync<Shelf>()).ToList();
                
                GetResultInfomation = new()
                {
                    Status = [],
                    Commands = commands,
                    Shelves = shelves
                };

                return GetResultInfomation;
            }
            catch (Exception)
            {
                //_logger.LogError(ex, "DB接続異常");
                throw;
            }
        }
    }
    public async Task InsertCommandsAsync(Command insertData)
    {
        using (var connection = new SqlConnection(connectionString))
        {
            try
            {
                var sqlCombined = @"
                    -- 搬送指示IDを格納する変数を定義
                    DECLARE @OutputTable TABLE (id VARCHAR(10));

                    -- INSERTと同時に、生成された搬送指示IDを変数に直接代入する
                    INSERT INTO commands (
                        carrier_id, command_type, eqp_name, location, reception_at, command_status
                    )
                    OUTPUT INSERTED.command_id INTO @OutputTable
                    VALUES (
                        @CarrierId, @CommandType, @EqpName, @Location, @ReceptionAt, @CommandStatus
                    );

                    -- CommandTypeが0なら棚をアップデート
                    IF @CommandType = 0
                    BEGIN
                        UPDATE shelves
                        SET reservation = (SELECT id FROM @OutputTable)
                        WHERE shelf_location = @Location;
                    END
                    ";

                // C#側は結果を受け取らないので ExecuteAsync で一発実行するだけ
                await connection.ExecuteAsync(sqlCombined, insertData);
            }
            catch (Exception ex)
            {
                throw;
            }
        }
    }
    public async Task<Command> GetCommandRequestAsync(string eqpName)
    {
        using (var connection = new SqlConnection(connectionString))
        {
            try
            {
                var sql = @"
                    -- 後半の処理で使い回すための変数を宣言
                    DECLARE @SelectedId VARCHAR(10), @SelectedType INT, @SelectedLocation VARCHAR(50);

                    -- 条件（0→1）に合う最も古い未送信の1件を特定
                    WITH TargetCommand AS (
                        SELECT TOP 1 *
                        FROM commands
                        WHERE command_status = 0 
                        AND eqp_name = @EqpName
                        ORDER BY 
                        command_type ASC,
                        reception_at ASC
                    )
                    -- 送信時刻に「GETDATE()」を直接指定して、SQLの実行瞬間の時刻を記録
                    UPDATE TargetCommand
                    SET 
                    send_at = GETDATE(),
                    command_status = 1,
                    @SelectedId = command_id,
                    @SelectedType = command_type,
                    @SelectedLocation = location;

                    -- 出庫（0）の時だけ、棚の予約を更新
                    IF @SelectedType = 0
                    BEGIN
                        UPDATE shelves
                        SET reservation = @SelectedId
                        WHERE shelf_location = @SelectedLocation;
                    END

                    -- C#（Dapper）へ返すデータをSELECT（send_atは除外）
                    SELECT 
                    command_id AS CommandId,
                    command_type AS CommandType,
                    carrier_id AS CarrierId,
                    eqp_name AS EqpName,
                    location AS Location,
                    reception_at AS ReceptionAt,
                    send_at AS SendAt,
                    completion_at AS CompletionAt,
                    command_status AS CommandStatus
                    FROM commands
                    WHERE command_id = @SelectedId;";

                RequestCommand = await connection.QuerySingleOrDefaultAsync<Command>(sql, new { EqpName = eqpName });

                return RequestCommand;
            }
            catch (Exception)
            {
                //_logger.LogError(ex, "DB接続異常");
                throw;
            }
        }
    }
    public async Task UpdateCommandStatusAsync(string commandId, int commandStatus)
    {
        using (var connection = new SqlConnection(connectionString))
        {
            try
            {
                var sql = @"
                        UPDATE commands 
                        SET command_status = @CommandStatus 
                        WHERE command_id = @CommandId;";

                await connection.ExecuteAsync(sql, new
                {
                    CommandStatus = commandStatus,
                    CommandId = commandId
                });

            }
            catch (Exception)
            {
                //_logger.LogError(ex, "DB接続異常");
                throw;
            }
        }
    }
    public async Task UpdateStatusAndTimeAsync(EquipmentCommand completion, DateTime CompletionAt)
    {
        using (var connection = new SqlConnection(connectionString))
        {
            try
            {
                // 1回の通信で両方のテーブルを条件付きで更新するSQL
                var sql = @"
                -- commandsテーブルの更新（入庫・出庫共通）
                UPDATE commands
                SET 
                    command_status = @CommandStatus,
                    completion_at = @CompletionAt
                WHERE 
                    command_id = @CommandId;

                -- shelvesテーブルの更新（CommandTypeで分岐）
                IF @CommandType = 1
                BEGIN
                    -- 入庫の場合：キャリアIDと入庫時刻を更新
                    UPDATE shelves
                    SET 
                        stored_carrier_id = @CarrierId,
                        storage_at = @CompletionAt
                    WHERE 
                        shelf_location = @Location;
                END
                ELSE IF @CommandType = 0
                BEGIN
                    -- 出庫の場合：キャリアID、入庫時刻、予約をnullにする
                    UPDATE shelves
                    SET 
                        stored_carrier_id = NULL,
                        reservation = NULL,
                        storage_at = NULL
                    WHERE 
                        shelf_location = @Location;
                END";
                var parameters = new
                {
                    CommandId = completion.CommandId,
                    CommandType = completion.CommandType,
                    CarrierId = completion.CarrierId,
                    Location = completion.Location,        
                    CommandStatus = completion.CommandStatus,
                    CompletionAt = CompletionAt             
                };
                await connection.ExecuteAsync(sql, parameters);
            }
            catch (Exception)
            {
                //_logger.LogError(ex, "DB接続異常");
                throw;
            }
        }
    }

    public async Task<List<Shelf>> GetShelfAsync(string prefix)
    {
        using (var connection = new SqlConnection(connectionString))
        {
            try
            {
                var sql = @"
                        SELECT shelf_location AS ShelfLocation,
                        stored_carrier_id AS StoredCarrierId,
                        reservation AS Reservation,
                        storage_at AS StorageAt
                        FROM shelves
                        WHERE shelf_location LIKE @Prefix
                        ; ";

                var result = await connection.QueryAsync<Shelf>(sql, new { Prefix = prefix });
                ShelfList = result.ToList();
            }
            catch (Exception)
            {
                //_logger.LogError(ex, "DB接続異常");
                throw;
            }
        }
        return ShelfList;
    }
}
