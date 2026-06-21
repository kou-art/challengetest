using System.ComponentModel.DataAnnotations;

namespace Final.Models;

public class EquipmentCommand
{
    [Required(ErrorMessage = "搬送指示IDが未入力または空白です。")]
    public string CommandId { get; set; }
    [Required(ErrorMessage = "出庫か入庫を選択してください。")]
    public int? CommandType { get; set; }
    [Required(ErrorMessage = "キャリアIDが未入力または空白です。")]
    public string CarrierId { get; set; }
    [Required(ErrorMessage = "設備IDが未入力または空白です。")]
    public string EqpName { get; set; }
    [Required(ErrorMessage = "棚IDが未入力または空白です。")]
    public string Location { get; set; }
    [Required(ErrorMessage = "搬送指示IDが未入力または空白です。")]
    public int? CommandStatus { get; set; }
}
