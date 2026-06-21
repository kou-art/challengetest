using Final.Repositories;
using Final.Services;
using Scalar.AspNetCore;
using System.Text.Json;

namespace Final
{
    public class Program
    {
        public static void Main(string[] args)
        {
            var builder = WebApplication.CreateBuilder(args);
            builder.Services.AddEndpointsApiExplorer();
            builder.Services.AddSwaggerGen();
            builder.Services.AddSingleton<SqlRepository>();
            builder.Services.AddSingleton<ShelfSystemService>();
            builder.Services.AddControllers()
            .AddJsonOptions(options =>
            {
                 options.JsonSerializerOptions.PropertyNameCaseInsensitive = true;
                options.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase;
            });

            builder.Services.AddCors(options =>
            {
                options.AddPolicy("AllowFetch", policy =>
                {
                    policy
                        .WithOrigins("")
                        .AllowAnyHeader()
                        .AllowAnyMethod();
                });
            });
            builder.Services.AddHttpClient();
            // Add services to the container.
            builder.Services.AddRazorPages();

            var app = builder.Build();
            try
            {
                // app.Services から直接 Singleton のインスタンスを取り出して実行
                var shelfService = app.Services.GetRequiredService<ShelfSystemService>();
                shelfService.GetAllEqpStateAsync().GetAwaiter().GetResult();
            }
            catch (Exception ex) 
            {
                Console.WriteLine("【起動時通信テスト】想定通りに失敗しました！");
                Console.WriteLine(ex.ToString());
            }
            if (app.Environment.IsDevelopment())
            {
                app.MapSwagger();
                // ★Scalarを有効化
                app.MapScalarApiReference(options =>
                {
                    options.WithOpenApiRoutePattern("/swagger/{documentName}/swagger.json");
                });
            }
            // Configure the HTTP request pipeline.
            if (!app.Environment.IsDevelopment())
            {
                app.UseExceptionHandler("/Error");
                // The default HSTS value is 30 days. You may want to change this for production scenarios, see https://aka.ms/aspnetcore-hsts.
                app.UseHsts();
            }
            app.UseCors("AllowFetch");
            app.UseHttpsRedirection();
            app.UseStaticFiles();

            app.UseRouting();

            app.UseAuthorization();
            app.MapControllers();
            app.MapRazorPages();

            app.Run();
        }
    }
}
