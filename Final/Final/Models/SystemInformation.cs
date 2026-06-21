namespace Final.Models;

public class SystemInformation
{
    public List<EquipmentState> Status { get; set; }
    public List<Command> Commands { get; set; }
    public List<Shelf> Shelves { get; set; }
}
