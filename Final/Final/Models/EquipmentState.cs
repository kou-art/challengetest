using System.ComponentModel.DataAnnotations;

namespace Final.Models;

public class EquipmentState
{
    [Required(ErrorMessage = "設備IDが未入力または空白です。")]
    public string EqpName { get; set; }
    [Required(ErrorMessage = "ControlStateが未入力または空白です。")]
    public int? ControlState { get; set; }
    [Required(ErrorMessage = "EquipmentStatusが未入力または空白です。")]
    public int? EquipmentStatus { get; set; }
    [Required(ErrorMessage = "AlarmStatusが未入力または空白です。")]
    public int? AlarmStatus { get; set; }
}
