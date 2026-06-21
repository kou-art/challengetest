using System.ComponentModel.DataAnnotations;

namespace Final.Models;

public class RelayCommand
{
    public string CommandId { get; set; }
    public string CarrierId { get; set; }
    [Required(ErrorMessage = "設備IDが未入力または空白です。")]
    public string EqpName { get; set; }
}
