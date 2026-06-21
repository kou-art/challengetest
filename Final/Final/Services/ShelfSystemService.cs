using Final.Models;
using Final.Repositories;
using System.Net;
using System.Text.RegularExpressions;

namespace Final.Services;

public class ShelfSystemService
{
    private readonly SqlRepository _repository;
    private readonly HttpClient _httpClient;
    public ShelfSystemService(
        SqlRepository repository,
        HttpClient httpClient)
    {
        _repository = repository;
        _httpClient = httpClient;
    }

    public List<EquipmentState> eqpStatusList = [
            new(){EqpName = "EQP01", ControlState = 0, EquipmentStatus = 0, AlarmStatus = 0 },
            new(){EqpName = "EQP02", ControlState = 0, EquipmentStatus = 0, AlarmStatus = 0 },
            new(){EqpName = "EQP03", ControlState = 0, EquipmentStatus = 0, AlarmStatus = 0}
        ];

    private readonly List<string> eqpBaseUrls = [
            "http://localhost:8090",
            "http://localhost:8091",
            "http://localhost:8092"
        ];

    public async Task GetAllEqpStateAsync()
    {
        List<Task> tasks = eqpBaseUrls.Select(u => GetEqpStateAsync(u)).ToList();

        await Task.WhenAll(tasks);
    }
    public async Task GetEqpStateAsync(string url)
    {
        try
        {
            var response = await _httpClient.GetAsync($"{url}/api/shelf-system/status");

            if (response.IsSuccessStatusCode)
            {
                var eqpState = await response.Content.ReadFromJsonAsync<EquipmentState>();
                var targetEqp = eqpStatusList.First(e => e.EqpName == eqpState.EqpName);
                targetEqp.ControlState = eqpState.ControlState;
                targetEqp.AlarmStatus = eqpState.AlarmStatus;

            }
        }
        catch (Exception)
        {
            throw;
        }

    }
    public async Task InsertValidationAsync(InsertCommand newCommand)
    {
        if (!Regex.IsMatch(newCommand.CarrierId, @"^CAR[0-9]{6}$"))
        {
            throw new HttpRequestException("キャリアID の命名規則が不正です。", null, System.Net.HttpStatusCode.BadRequest);
        }
        if (newCommand.EqpName != "EQP01" && newCommand.EqpName != "EQP02" && newCommand.EqpName != "EQP03")
        {
            throw new HttpRequestException("設備IDが存在しません。", null, System.Net.HttpStatusCode.NotFound);
        }
        var targetEqp = eqpStatusList.First(e => e.EqpName == newCommand.EqpName);
        if (targetEqp.ControlState == 0)
        {
            throw new HttpRequestException("指定された設備がOFFLINEです。", null, HttpStatusCode.BadRequest);
        }

        string availableLocation = "";
        string prefix = "";
        if (newCommand.EqpName == "EQP01") { prefix = "1%"; }
        else if (newCommand.EqpName == "EQP02") { prefix = "2%"; }
        else if (newCommand.EqpName == "EQP03") { prefix = "3%"; }
        var shelfList = await _repository.GetShelfAsync(prefix);
        bool isCarrierAlreadyStored = shelfList.Any(s => s.StoredCarrierId == newCommand.CarrierId);
        Shelf? selectedInShelf = shelfList.FirstOrDefault(s => s.StoredCarrierId == null);
        bool isAllEmpty = shelfList.Any(s => s.StoredCarrierId != null);
        Shelf? matchedShelf = shelfList.FirstOrDefault(s => s.StoredCarrierId == newCommand.CarrierId);
        if (newCommand.CommandType == 1)
        {
            if (isCarrierAlreadyStored)
            {
                throw new HttpRequestException("指定されたキャリアIDは既に入庫されています。", null, HttpStatusCode.BadRequest);
            }
            if (selectedInShelf == null)
            {
                throw new HttpRequestException("棚が満帆のため入庫できません。", null, HttpStatusCode.BadRequest);
            }
            else if (selectedInShelf != null)
            {
                availableLocation = selectedInShelf.ShelfLocation;
            }
        }
        else
        {
            if (!isAllEmpty)
            {
                throw new HttpRequestException("棚が空のため出庫できません。", null, HttpStatusCode.BadRequest);
            }
            if (matchedShelf == null)
            {
                throw new HttpRequestException("指定されたキャリアIDは棚に存在しません。", null, HttpStatusCode.NotFound);
            }
            else if (matchedShelf.Reservation != null)
            {
                throw new HttpRequestException("指定されたキャリアがある棚は、すでに予約があります。", null, HttpStatusCode.BadRequest);
            }

            availableLocation = matchedShelf.ShelfLocation;
        }
        
        Command insertData = new Command()
        {
            CarrierId = newCommand.CarrierId,
            CommandType = (int)newCommand.CommandType,
            EqpName = newCommand.EqpName,
            Location = availableLocation,
            ReceptionAt = DateTime.Now,
            SendAt = null,
            CompletionAt = null,
            CommandStatus = 0
        };
        await _repository.InsertCommandsAsync(insertData);
    }

    public void UpdateEqpStatus(string eqpName, string endPoint)
    {
        var targetEqp = eqpStatusList.First(e => e.EqpName == eqpName);
        if (endPoint == "online") targetEqp.ControlState = 1;
        else if (endPoint == "start") targetEqp.EquipmentStatus = 1;
        else if (endPoint == "completion") targetEqp.EquipmentStatus = 0;
        else if (endPoint == "incident") targetEqp.AlarmStatus = 1;
        else if (endPoint == "recovery") targetEqp.AlarmStatus = 0;
    }

    public async Task<bool> UnloadValidationAsync(RelayCommand unload, string endPoint)
    {
        if (unload.EqpName != "Eqp01" && unload.EqpName != "Eqp02" && unload.EqpName != "Eqp03")
        {
            return false;
        }
        await PostHttpClientAsync(unload, endPoint);
        return true;
    }

    public async Task PostHttpClientAsync(RelayCommand sendCommand, string endPoint)
    {
        string url = "";
        if (sendCommand.EqpName == "EQP01") url = eqpBaseUrls[0];
        else if (sendCommand.EqpName == "EQP02") url = eqpBaseUrls[1];
        else if (sendCommand.EqpName == "EQP03") url = eqpBaseUrls[2];

        try
        {
            var response = await _httpClient.PostAsJsonAsync($"{url}/api/shelf-system/{endPoint}", sendCommand);
        }
        catch (Exception)
        {
            throw;
        }
    }
}
