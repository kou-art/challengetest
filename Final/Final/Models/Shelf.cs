namespace Final.Models;

public class Shelf
{
    public string ShelfLocation { get; set; }
    public string? StoredCarrierId { get; set; }
    public string? Reservation { get; set; }
    public DateTime? StorageAt { get; set; }
}
