using System.ComponentModel.DataAnnotations;

namespace Final.Models;

public class InsertCommand
{
    [Required(ErrorMessage = "出庫か入庫を選択してください。")]
    [Range(0, 1, ErrorMessage = "出庫(0)、入庫(1)を指定してください。")]
    public int? CommandType { get; set; }
    [Required(ErrorMessage = "キャリアIDが未入力または空白です。")]
    public string CarrierId { get; set; }
    [Required(ErrorMessage = "設備IDが未入力または空白です。")]
    public string EqpName { get; set; }
}
