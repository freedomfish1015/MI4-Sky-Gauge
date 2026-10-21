using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Web.Script.Serialization;

namespace Mi4Sky {
 static class Tests {
  static int passed;
  static void Assert(bool ok,string name) {if(!ok)throw new Exception(name);Console.WriteLine("PASS "+name);passed++;}
  static void Reject(string name,Action action) {
   bool rejected=false;try{action();}catch(Exception){rejected=true;} Assert(rejected,name);
  }
  public static int Main() {
   string dir=Path.Combine(Path.GetTempPath(),"Mi4-Sky-Tests-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(dir);
   string boot=Path.Combine(dir,"boot.img"), root=Path.Combine(dir,"rootfs.sparse.img");
   using(var f=File.Create(boot)){byte[] magic=Encoding.ASCII.GetBytes("ANDROID!");f.SetLength(33554432);f.Write(magic,0,8);f.Position=524288;f.Write(magic,0,8);}
   using(var w=new BinaryWriter(File.Create(root))) {
    w.Write(0xed26ff3au);w.Write((ushort)1);w.Write((ushort)0);w.Write((ushort)28);w.Write((ushort)12);
    w.Write(4096u);w.Write(524288u);w.Write(1u);w.Write(0u);
    w.Write((ushort)0xcac3);w.Write((ushort)0);w.Write(524288u);w.Write(12u);
   }
   var m=new Manifest {format=1,product="mi4-sky",version="TEST-FIXTURE-DO-NOT-FLASH",installer_min=1,
    profile="mi4-lte-jdi-mxt640t",install_mode="clean-stock-fastboot",boot_partition_bytes=33554432,
    root_uuid="93afcbbe-875f-49b0-83da-ee8193f20ca5",rootfs_bytes=2147483648L,
    validation="candidate-not-clean-flash-tested",files=new[]{
     new ImageFile{name="boot.img",size=new FileInfo(boot).Length,sha256=ImagePackage.Hash(boot)},
     new ImageFile{name="rootfs.sparse.img",size=new FileInfo(root).Length,sha256=ImagePackage.Hash(root)}}};
   Func<string,bool,bool,string> create=(name,unknown,duplicate)=> {
    string path=Path.Combine(dir,name+".mi4sky");
    using(var z=ZipFile.Open(path,ZipArchiveMode.Create)) {
     using(var w=new StreamWriter(z.CreateEntry("manifest.json").Open(),new UTF8Encoding(false)))w.Write(new JavaScriptSerializer().Serialize(m));
     z.CreateEntryFromFile(boot,"boot.img");z.CreateEntryFromFile(root,"rootfs.sparse.img");
     if(unknown)z.CreateEntry("../escape");if(duplicate)z.CreateEntry("boot.img");
    }return path;
   };
   var valid=ImagePackage.Load(create("valid",false,false),s=>{});
   Assert(valid.Info.version==m.version,"valid offline fixture and sparse structure");
   Reject("path traversal entry",()=>ImagePackage.Load(create("traversal",true,false),s=>{}));
   Reject("duplicate entry",()=>ImagePackage.Load(create("duplicate",false,true),s=>{}));
   m.files[1].sha256=new string('0',64);
   Reject("payload hash mismatch",()=>ImagePackage.Load(create("bad-hash",false,false),s=>{}));
   m.files[1].sha256=ImagePackage.Hash(root);m.root_uuid="bad";
   Reject("incompatible UUID",()=>ImagePackage.Load(create("bad-uuid",false,false),s=>{}));
   m.root_uuid="93afcbbe-875f-49b0-83da-ee8193f20ca5";m.installer_min=4;
   Reject("future format requires new installer",()=>ImagePackage.Load(create("future",false,false),s=>{}));
   m.installer_min=3;m.validation="runtime-user-accepted-not-clean-flash-tested";
   m.release_channel="stable-profile-only";m.runtime_build="2026.10.21-candidate-r2";
   Assert(ImagePackage.Load(create("stable-profile",false,false),s=>{}).Info.validation==m.validation,"scoped user-accepted runtime release");
   m.release_channel=null;
   Reject("stable scope missing",()=>ImagePackage.Load(create("stable-missing-scope",false,false),s=>{}));
   m.release_channel="stable-profile-only";m.installer_min=2;
   Reject("old installer policy for stable scope",()=>ImagePackage.Load(create("stable-old-policy",false,false),s=>{}));
   m.installer_min=1;m.validation="candidate-not-clean-flash-tested";m.rootfs_bytes=4294967296L;
   Reject("sparse expanded size mismatch",()=>ImagePackage.Load(create("bad-size",false,false),s=>{}));
   Assert(Fastboot.Size("0x02000000")==33554432 && Fastboot.Size("33554432")==33554432,"partition number parser");
   Reject("invalid partition size",()=>Fastboot.Size("unknown"));
   Assert(Fastboot.ParseVariable("product: MSM8974\r\nFinished. Total time: 0.001s\r\n","product",false)=="MSM8974","stock product parser");
   Assert(Fastboot.ParseVariable("(bootloader) partition-size:boot: 0x02000000\r\n","partition-size:boot",false)=="0x02000000","prefixed nested key parser");
   Assert(Fastboot.ParseVariable("version-bootloader: \r\nFinished. Total time: 0.002s\r\n","version-bootloader",true)=="","empty variable never captures Finished");
   Reject("required empty variable",()=>Fastboot.ParseVariable("partition-size:boot: \r\nFinished. Total time: 0.002s\r\n","partition-size:boot",false));
   Reject("missing variable",()=>Fastboot.ParseVariable("Finished. Total time: 0.002s\r\n","product",true));
   Reject("duplicate variable",()=>Fastboot.ParseVariable("product: MSM8974\nproduct: other\n","product",false));
   Reject("wrong variable key",()=>Fastboot.ParseVariable("not-product: MSM8974\n","product",false));
   Reject("untrusted fastboot binary",()=>new Fastboot(dir,s=>{}));
   Console.WriteLine("OFFLINE TESTS PASSED="+passed+"; NO USB COMMANDS EXECUTED; fixtures at "+dir);
   return 0;
  }
 }
}
