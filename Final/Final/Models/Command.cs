namespace Final.Models;

public class Command
{
    public string CommandId { get; set; }
    public int CommandType { get; set; }
    public string CarrierId { get; set; }
    public string EqpName { get; set; }
    public string Location { get; set; }
    public DateTime ReceptionAt { get; set; }
    public DateTime? SendAt { get; set; }
    public DateTime? CompletionAt { get; set; }
    public int CommandStatus { get; set; }
}
