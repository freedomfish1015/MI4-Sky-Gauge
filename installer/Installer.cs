using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace Mi4Sky {
 public sealed class ImageFile { public string name; public long size; public string sha256; }
 public sealed class Manifest {
  public int format; public string product; public string version; public int installer_min;
  public string profile; public string install_mode; public long boot_partition_bytes;
  public string root_uuid; public long rootfs_bytes; public string validation;
  public string[] bundled_repairs;
  public string release_channel; public string runtime_build;
  public ImageFile[] files;
 }
 public sealed class ImagePackage {
  public Manifest Info; public string Boot; public string Rootfs;
  public static string Hash(string path) {
   using(var stream=File.OpenRead(path)) using(var sha=SHA256.Create())
    return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
  }
  public static ImagePackage Load(string path, Action<string> log) {
   var result=new ImagePackage();
   string dir=Path.Combine(Path.GetTempPath(), "MI4-Sky-"+Guid.NewGuid().ToString("N"));
   Directory.CreateDirectory(dir);
   using(var zip=ZipFile.OpenRead(path)) {
    var entries=zip.Entries.ToArray();
    string[] allowed={"manifest.json", "boot.img", "rootfs.sparse.img", "LICENSES.txt"};
    if(entries.Length<3 || entries.Length>4 || entries.Any(e=>!allowed.Contains(e.FullName)) ||
       entries.Select(e=>e.FullName).Distinct().Count()!=entries.Length)
     throw new InvalidDataException("系统包包含重复、未知或不安全路径。请勿使用此包。");
    var m=zip.GetEntry("manifest.json");
    if(m==null || m.Length>32768) throw new InvalidDataException("缺少或无效的 manifest.json");
    using(var reader=new StreamReader(m.Open(), Encoding.UTF8))
     result.Info=new JavaScriptSerializer().Deserialize<Manifest>(reader.ReadToEnd());
    Manifest info=result.Info;
    if(info==null || info.format!=1 || info.installer_min>3 || info.installer_min<1 ||
       info.product!="mi4-sky" || info.profile!="mi4-lte-jdi-mxt640t" ||
       info.install_mode!="clean-stock-fastboot" || info.boot_partition_bytes!=33554432 ||
       info.root_uuid!="93afcbbe-875f-49b0-83da-ee8193f20ca5" ||
       info.rootfs_bytes<2147483648L || info.rootfs_bytes>8589934592L ||
       info.files==null || info.files.Length!=2 || String.IsNullOrWhiteSpace(info.version) ||
       info.version.Length>100 || (info.validation!="candidate-not-clean-flash-tested" && info.validation!="clean-flash-tested" &&
       info.validation!="runtime-user-accepted-not-clean-flash-tested"))
     throw new InvalidDataException("系统包版本或兼容性不受此版程序支持。");
    if(info.validation=="runtime-user-accepted-not-clean-flash-tested" &&
       (info.installer_min<3 || info.release_channel!="stable-profile-only" || info.runtime_build!="2026.10.21-candidate-r2"))
     throw new InvalidDataException("稳定运行与安装验收的范围声明缺失。");
    if(info.files.Select(f=>f.name).Distinct().Count()!=2 ||
       !info.files.Any(f=>f.name=="boot.img") || !info.files.Any(f=>f.name=="rootfs.sparse.img"))
     throw new InvalidDataException("镜像清单不完整。");
    long required=info.files.Sum(f=>f.size)+1073741824L;
    if(new DriveInfo(Path.GetPathRoot(dir)).AvailableFreeSpace<required)
     throw new IOException("临时目录所在磁盘空间不足：至少需要镜像展开体积再加 1GB。");
    foreach(var f in info.files) {
     var entry=zip.GetEntry(f.name);
     if(entry==null || f.size<=0 || f.size>8589934592L || entry.Length!=f.size ||
        !Regex.IsMatch(f.sha256??"", "^[a-f0-9]{64}$"))
      throw new InvalidDataException("镜像大小或校验信息不正确。");
     string target=Path.Combine(dir, f.name);
     log("解压并校验 "+f.name+" …");
     entry.ExtractToFile(target, false);
     if(Hash(target)!=f.sha256) throw new InvalidDataException("SHA-256 校验失败："+f.name);
    }
   }
   result.Boot=Path.Combine(dir,"boot.img"); result.Rootfs=Path.Combine(dir,"rootfs.sparse.img");
   CheckBoot(result.Boot); CheckSparse(result.Rootfs,result.Info.rootfs_bytes);
   log("镜像完整性校验通过："+result.Info.version+"，验证状态："+result.Info.validation);
   return result;
  }
  static void CheckBoot(string path) {
   using(var r=new BinaryReader(File.OpenRead(path))) {
    if(r.BaseStream.Length!=33554432 || Encoding.ASCII.GetString(r.ReadBytes(8))!="ANDROID!")
     throw new InvalidDataException("完整 boot 分区镜像无效。");
    r.BaseStream.Position=524288;
    if(Encoding.ASCII.GetString(r.ReadBytes(8))!="ANDROID!")
     throw new InvalidDataException("缺少 Linux boot 镜像或 lk2nd 偏移不符。");
   }
  }
  static void CheckSparse(string path,long expected) {
   using(var r=new BinaryReader(File.OpenRead(path))) {
    if(r.ReadUInt32()!=0xed26ff3a || r.ReadUInt16()!=1) throw new InvalidDataException("不是 Android sparse 镜像。");
    r.ReadUInt16(); ushort header=r.ReadUInt16(), chunkHeader=r.ReadUInt16();
    uint block=r.ReadUInt32(), blocks=r.ReadUInt32(), chunks=r.ReadUInt32(); r.ReadUInt32();
    if(header<28 || chunkHeader<12 || block!=4096 || (long)block*blocks!=expected || chunks==0)
     throw new InvalidDataException("sparse 镜像结构/展开大小无效。");
    r.BaseStream.Position=header; long count=0;
    for(uint i=0;i<chunks;i++) {
     if(r.BaseStream.Position+chunkHeader>r.BaseStream.Length) throw new InvalidDataException("sparse 截断。");
     ushort type=r.ReadUInt16(); r.ReadUInt16(); uint n=r.ReadUInt32(), size=r.ReadUInt32();
     long data=(long)size-chunkHeader;
     if(data<0 || (type==0xcac1 && data!=(long)n*block) ||
        (type==0xcac2 && data!=4) || (type==0xcac3 && data!=0) ||
        (type==0xcac4 && (data!=4 || n!=0)) || type<0xcac1 || type>0xcac4)
      throw new InvalidDataException("sparse 分块无效。");
     long next=r.BaseStream.Position+(chunkHeader-12)+data;
     if(next>r.BaseStream.Length) throw new InvalidDataException("sparse 数据截断。");
     r.BaseStream.Position=next; count+=n;
    }
    if(count!=blocks || r.BaseStream.Position!=r.BaseStream.Length) throw new InvalidDataException("sparse 大小不匹配。");
   }
  }
 }
 public sealed class Fastboot {
  readonly string exe; readonly Action<string> log;
  public Fastboot(string folder,Action<string> logger) {
   log=logger; exe=Path.Combine(folder,"fastboot.exe");
   var trusted=new Dictionary<string,string> {
    {"fastboot.exe","0fcd728122cfd2ed6ab2baaf98070ab484c1d55a4b4b20f6ae663ec3837801fb"},
    {"AdbWinApi.dll","d60103a5e99bc9888f786ee916f5d6e45493c3247972cb053833803de7e95cf9"},
    {"AdbWinUsbApi.dll","25207c506d29c4e8dceb61b4bd50e8669ba26012988a43fbf26a890b1e60fc97"}
   };
   foreach(var item in trusted) if(!File.Exists(Path.Combine(folder,item.Key)) ||
     ImagePackage.Hash(Path.Combine(folder,item.Key))!=item.Value)
    throw new InvalidDataException("刷机工具缺失或被修改："+item.Key);
  }
  public string Run(string args,int timeout) {
   log("fastboot "+args);
   var start=new ProcessStartInfo(exe,args) {UseShellExecute=false,CreateNoWindow=true,
    RedirectStandardOutput=true,RedirectStandardError=true};
   using(var p=Process.Start(start)) {
    Task<string> stdout=p.StandardOutput.ReadToEndAsync(), stderr=p.StandardError.ReadToEndAsync();
    if(!p.WaitForExit(timeout)) {try{p.Kill();}catch{} throw new IOException("USB 命令超时。不要盲目拔线，请保留日志并重新检查 Fastboot。");}
    string output=stdout.Result+stderr.Result; log(output.Trim());
    if(p.ExitCode!=0 || Regex.IsMatch(output,@"\bFAIL(?:ED)?\b",RegexOptions.IgnoreCase))
     throw new IOException("Fastboot 拒绝了命令。已停止，不会继续刷写。\r\n"+output);
    return output;
   }
  }
  public string Single() {
   var devices=Regex.Matches(Run("devices",15000),@"(?m)^([A-Za-z0-9_.:-]+)\s+fastboot\s*$");
   if(devices.Count!=1) throw new IOException("必须恰好连接一台 Fastboot 手机，当前数量："+devices.Count);
   return devices[0].Groups[1].Value;
  }
  public static string ParseVariable(string output,string key,bool allowEmpty) {
   // Never let whitespace consume the next line (e.g. fastboot's Finished message).
   var matches=Regex.Matches(output,@"(?m)^(?:\(bootloader\)[ \t]*)?"+
    Regex.Escape(key)+@":[ \t]*([^\r\n]*)\r?$");
   if(matches.Count!=1) throw new IOException("设备参数缺失或重复："+key);
   string value=matches[0].Groups[1].Value.Trim();
   if(value.Length==0 && !allowEmpty) throw new IOException("设备未报告必需参数："+key);
   return value;
  }
  public string Get(string serial,string key) {
   return ParseVariable(Run("-s "+serial+" getvar "+key,15000),key,false);
  }
  public void Diagnose() {
   // Read-only. Missing values do not imply stock mode or authorize flashing.
   string serial=Single();
   foreach(string key in new[]{"product","version","kernel","version-bootloader",
     "lk2nd:version","lk2nd:model","partition-size:boot","partition-size:lk2nd",
     "partition-size:userdata","partition-size:system","partition-size:cache"}) {
    string value=ParseVariable(Run("-s "+serial+" getvar "+key,15000),key,true);
    log("INSPECT "+key+"="+(value.Length==0?"<empty>":value));
   }
   log("只读检测完成。未刷写、未擦除，也未确认设备满足安装条件。");
  }
  public static long Size(string value) {
   long size;
   if(value.StartsWith("0x",StringComparison.OrdinalIgnoreCase)) {
    if(!Int64.TryParse(value.Substring(2),NumberStyles.HexNumber,CultureInfo.InvariantCulture,out size)) throw new IOException("分区大小格式错误");
   } else if(!Int64.TryParse(value,out size)) throw new IOException("分区大小格式错误");
   return size;
  }
  public string Inspect(ImagePackage package) {
   string serial=Single();
   string product=Get(serial,"product"), version=Get(serial,"version-bootloader");
   if(product!="MSM8974" || version.IndexOf("lk2nd",StringComparison.OrdinalIgnoreCase)>=0)
    throw new IOException("需要原厂 FASTBOOT 兔子界面；不支持直接在 lk2nd 的 boot 偏移模式刷完整包。未知机型也会停止。");
   long boot=Size(Get(serial,"partition-size:boot")), userdata=Size(Get(serial,"partition-size:userdata"));
   if(boot!=33554432 || userdata<package.Info.rootfs_bytes || userdata>137438953472L)
    throw new IOException("分区布局不受支持。没有执行刷写。");
   log("目标 "+serial+"，product="+product+"，boot="+boot+"，userdata="+userdata);
   return serial;
  }
  public void Flash(ImagePackage package,string expectedSerial) {
   foreach(var f in package.Info.files) {
    string path=f.name=="boot.img"?package.Boot:package.Rootfs;
    if(ImagePackage.Hash(path)!=f.sha256) throw new IOException("校验后的临时镜像已改变，停止刷写。");
   }
   string serial=Inspect(package);
   if(serial!=expectedSerial) throw new IOException("设备发生变化，必须重新确认。");
   // Windows writes only userdata/boot. R2 first boot may separately repair one
   // exact-version aboot sector. A failed rootfs write never triggers boot flashing.
   Run("-s "+serial+" -S 128M flash userdata \""+package.Rootfs+"\"",1800000);
   Run("-s "+serial+" flash boot \""+package.Boot+"\"",300000);
   Run("-s "+serial+" reboot",30000);
   log("Fastboot 已报告刷写成功并发出重启。首次启动仍需人工检查，不能据此认定系统已启动。");
  }
 }
 public sealed class MainForm:Form {
  readonly TextBox output=new TextBox(); readonly Label state=new Label();
  readonly Button load=new Button(), flash=new Button(); readonly CheckBox hardware=new CheckBox(), charged=new CheckBox();
  ImagePackage package; Fastboot device; bool busy; readonly string logfile;
  public MainForm() {
   Text="MI4 Sky Gauge 安装器 3 · 安装流程测试版"; Width=900; Height=720; MinimumSize=new Size(760,640);
   Font=new Font("Microsoft YaHei UI",10); StartPosition=FormStartPosition.CenterScreen;
   string logs=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"MI4-Sky","logs");
   Directory.CreateDirectory(logs); logfile=Path.Combine(logs,DateTime.Now.ToString("yyyyMMdd-HHmmss")+".log");
   var panel=new TableLayoutPanel {Dock=DockStyle.Fill,Padding=new Padding(16),ColumnCount=1,RowCount=7};
   panel.RowStyles.Add(new RowStyle(SizeType.Absolute,104)); panel.RowStyles.Add(new RowStyle(SizeType.Absolute,44));
   panel.RowStyles.Add(new RowStyle(SizeType.Absolute,48)); panel.RowStyles.Add(new RowStyle(SizeType.Absolute,48));
   panel.RowStyles.Add(new RowStyle(SizeType.Absolute,48)); panel.RowStyles.Add(new RowStyle(SizeType.Absolute,50));
   panel.RowStyles.Add(new RowStyle(SizeType.Percent,100)); Controls.Add(panel);
   var warning=new Label {Dock=DockStyle.Fill,Text="完整重装将清空手机应用、照片和全部用户文件。\r\n仅限确认硬件的 MI 4 LTE；首次启动自动修复匹配的 aboot，有引导风险。\r\n系统稳定渠道不等于安装流程已验收；部分原厂参数仍不兼容，本程序会停止。",ForeColor=Color.Maroon};
   panel.Controls.Add(warning); load.Text="选择独立系统包（.mi4sky）"; load.AutoSize=true; panel.Controls.Add(load);
   state.Dock=DockStyle.Fill; state.Text="先选择系统包，再连接原厂 FASTBOOT 兔子界面的手机。"; panel.Controls.Add(state);
   hardware.Text="我已核实是 Mi4 LTE，JDI 屏 / Atmel mxt640t 触控（非米3、非未知屏幕）";
   hardware.Dock=DockStyle.Fill; panel.Controls.Add(hardware);
   charged.Text="已备份且允许清空此手机，电池充足（建议 ≥50%），数据线连接可靠"; charged.Dock=DockStyle.Fill; panel.Controls.Add(charged);
   flash.Text="检查目标并安装"; flash.AutoSize=true; flash.Enabled=false; panel.Controls.Add(flash);
   output.Multiline=true; output.ReadOnly=true; output.ScrollBars=ScrollBars.Both; output.Dock=DockStyle.Fill; output.WordWrap=false; panel.Controls.Add(output);
   load.Click+=async delegate {await LoadPackage();}; flash.Click+=async delegate {await Install();};
   FormClosing+=(s,e)=>{if(busy){e.Cancel=true; MessageBox.Show("操作进行中，请勿关闭安装器或拔线。");}};
   Log("本地日志："+logfile+"。不上传日志；日志可能包含设备序列号。");
  }
  void Log(string message) {
   if(InvokeRequired){Invoke(new Action<string>(Log),message);return;}
   string line=DateTime.Now.ToString("HH:mm:ss")+" "+message+Environment.NewLine;
   output.AppendText(line); File.AppendAllText(logfile,line,Encoding.UTF8);
  }
  void Busy(bool value) {busy=value;load.Enabled=!value;flash.Enabled=!value&&package!=null;hardware.Enabled=!value;charged.Enabled=!value;}
  async Task LoadPackage() {
   using(var dialog=new OpenFileDialog {Filter="MI4 系统包|*.mi4sky",Title="选择系统包（不会开始刷机）"}) {
    if(dialog.ShowDialog()!=DialogResult.OK)return;
    Busy(true); package=null;
    try {package=await Task.Run(()=>ImagePackage.Load(dialog.FileName,Log));
     state.Text="已校验："+package.Info.version+" · 安装流程尚未全量验收";
     device=new Fastboot(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"tools"),Log);
    } catch(Exception ex) {package=null;Log(ex.Message);MessageBox.Show(ex.Message,"系统包未通过校验");}
    finally {Busy(false);}
   }
  }
  async Task Install() {
   if(!hardware.Checked || !charged.Checked){MessageBox.Show("请先核实硬件、备份和供电条件。未知版本不要勾选。");return;}
   Busy(true);
   try {
    string serial=await Task.Run(()=>device.Inspect(package));
    if(MessageBox.Show("即将清空手机 "+serial+" 并安装 "+package.Info.version+"。\r\nWindows 阶段写 userdata 和 boot；R2 首次启动可能自动修复已知版本的 aboot，有引导风险。\r\n未知引导版本跳过修复，不能保证其他屏幕可用。\r\n已确认这是要刷写的手机？", "最后确认",MessageBoxButtons.YesNo,MessageBoxIcon.Warning,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)return;
    await Task.Run(()=>device.Flash(package,serial)); state.Text="刷写命令完成，请检查手机首次启动。";
   } catch(Exception ex) {Log("停止："+ex.Message);MessageBox.Show(ex.Message,"已停止，请保留日志");}
   finally {Busy(false);}
  }
 }
 static class Program {
  [STAThread] static int Main(string[] args) {
   if(args.Length==1 && args[0]=="--diagnose") {
    try {new Fastboot(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"tools"),
     s=>Console.WriteLine(s)).Diagnose();return 0;}
    catch(Exception ex){Console.Error.WriteLine(ex.Message);return 1;}
   }
   if(args.Length==2 && args[0]=="--verify") {
    try {ImagePackage.Load(args[1],s=>Console.WriteLine(s));return 0;}
    catch(Exception ex){Console.Error.WriteLine(ex.Message);return 1;}
   }
   Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new MainForm());return 0;
  }
 }
}
