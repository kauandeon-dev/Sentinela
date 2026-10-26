// Lançador da versão portátil do Sentinela para Windows.
//
// O mesmo programa, copiado com nomes diferentes, abre cada função da pasta
// (o nome do arquivo escolhe o modo; arrastar arquivos para cima dele também
// funciona). Ele só chama o Python embutido com o portatil.py na mesma
// janela, espera terminar e mantém a janela aberta para ler as mensagens.
//
//   Sentinela.exe          painel
//   Sentinela-Demo.exe     painel + banco de demonstração        (--demo)
//   Parar-Sentinela.exe    encerra o que roda em segundo plano    (--parar)
//   Trocar-Senha.exe       troca a senha do admin                 (--senha)
//   Descriptografar.exe    .sql das cópias arrastadas             (--decrypt)
//
// Compilado pelo portatil\montar.ps1 com o csc.exe que acompanha o Windows
// (.NET Framework 4): sem dependências além do próprio Windows 10/11.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;

[assembly: AssemblyTitle("Sentinela")]
[assembly: AssemblyProduct("Sentinela")]
[assembly: AssemblyDescription("Sentinela - backup automatizado de bancos de dados")]
[assembly: AssemblyCompany("Kauan V. Machado Deon")]
[assembly: AssemblyCopyright("Projeto Integrador IFSC")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

static class Lancador
{
    // Código de saída do portatil.py: o Sentinela roda em segundo plano (já
    // estava, ou a janela acabou de passar a vez) e o navegador foi aberto.
    const int SegundoPlano = 3;

    static int Main(string[] args)
    {
        string exe = Assembly.GetEntryAssembly().Location;
        string root = Path.GetDirectoryName(exe);
        string name = Path.GetFileNameWithoutExtension(exe).ToLowerInvariant();

        string mode = "", title = "Sentinela";
        if (name.Contains("demo")) { mode = "--demo"; title = "Sentinela (demonstração)"; }
        else if (name.Contains("parar")) { mode = "--parar"; title = "Sentinela - Encerrar"; }
        else if (name.Contains("senha")) { mode = "--senha"; title = "Sentinela - Trocar senha"; }
        else if (name.Contains("descriptograf")) { mode = "--decrypt"; title = "Sentinela - Descriptografar"; }
        try { Console.Title = title; } catch (IOException) { }
        try { Console.OutputEncoding = new UTF8Encoding(false); } catch (IOException) { }  // sem BOM

        string python = Path.Combine(Path.Combine(root, "python"), "python.exe");
        string script = Path.Combine(Path.Combine(root, "app"), "portatil.py");
        if (!File.Exists(python) || !File.Exists(script))
        {
            Console.WriteLine("Pasta incompleta: falta \"python\\python.exe\" ou \"app\\portatil.py\".");
            Console.WriteLine("Extraia o ZIP inteiro antes de abrir (botão direito no ZIP > Extrair Tudo)");
            Console.WriteLine("ou instale de novo com o Sentinela-Instalador.exe.");
            Pause();
            return 1;
        }

        var cmd = new StringBuilder(Quote(script));
        if (mode != "") cmd.Append(' ').Append(mode);
        foreach (string a in args) cmd.Append(' ').Append(Quote(a));

        var psi = new ProcessStartInfo(python, cmd.ToString());
        psi.UseShellExecute = false;          // mesma janela (console) do lançador
        psi.WorkingDirectory = root;
        psi.EnvironmentVariables["PYTHONUTF8"] = "1";

        // Ctrl+C é tratado pelo Python (encerra o painel e o banco de
        // demonstração); o lançador só espera ele terminar.
        Console.CancelKeyPress += delegate (object s, ConsoleCancelEventArgs e)
        {
            if (e.SpecialKey == ConsoleSpecialKey.ControlC) e.Cancel = true;
        };

        int code;
        using (Process p = Process.Start(psi))
        {
            p.WaitForExit();
            code = p.ExitCode;
        }
        if (code == SegundoPlano)
        {
            Thread.Sleep(4000);               // tempo de ler a mensagem; a janela fecha sozinha
            return 0;
        }
        if (mode == "" || mode == "--demo")
        {
            Console.WriteLine();
            Console.WriteLine("Sentinela encerrado.");
        }
        Pause();
        return code;
    }

    static void Pause()
    {
        if (Console.IsInputRedirected) return;
        Console.WriteLine();
        Console.Write("Pressione qualquer tecla para fechar . . .");
        try { Console.ReadKey(true); } catch (InvalidOperationException) { }
    }

    // Aspas no padrão do Windows (CommandLineToArgvW): caminhos com espaço,
    // acento, aspas e barras invertidas chegam inteiros ao Python.
    static string Quote(string a)
    {
        if (a.Length > 0 && a.IndexOfAny(new[] { ' ', '\t', '\n', '\v', '"' }) < 0) return a;
        var sb = new StringBuilder("\"");
        for (int i = 0; ; i++)
        {
            int slashes = 0;
            while (i < a.Length && a[i] == '\\') { i++; slashes++; }
            if (i == a.Length) { sb.Append('\\', slashes * 2); break; }
            if (a[i] == '"') { sb.Append('\\', slashes * 2 + 1).Append('"'); }
            else { sb.Append('\\', slashes).Append(a[i]); }
        }
        return sb.Append('"').ToString();
    }
}
