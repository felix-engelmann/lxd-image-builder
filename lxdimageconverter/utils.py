import sys
import subprocess
import tarfile
from jinja2 import Template
from datetime import datetime

from .conf import *

def parse_fdisk(fdisk_output):
    result = {}
    disk_type = "dos"
    for line in fdisk_output.split("\n"):
        if "Disklabel type: gpt" in line:
            disk_type = "gpt"
        if not line.startswith("/"):
            continue
        parts = line.split()
        print(parts)

        inf = {}
        if parts[1] == "*":
            inf['bootable'] = True
            del parts[1]

        else:
            inf['bootable'] = False

        inf['start'] = int(parts[1])
        inf['end'] = int(parts[2])
        inf['blocks'] = int(parts[3].rstrip("+"))
        inf['size'] = parts[4]
        if disk_type == "dos":
            inf['partition_id'] = int(parts[5], 16)
            inf['partition_id_string'] = " ".join(parts[6:])
        else:
            inf['partition_id'] = -1
            inf['partition_id_string'] = " ".join(parts[5:])

        result[parts[0]] = inf
    return result

def download_file(url):
    filename = url.split('/')[-1]
    print("downloading %s"%filename)

    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    downloadfile = os.path.join(DOWNLOAD_DIR,filename)
    if not os.path.exists(downloadfile):
        subprocess.run(['curl','-L','-O',url],cwd=DOWNLOAD_DIR)
    else:
        print("using cached download")
    return downloadfile


def extract_rootfs(file,osname):
    rootfile = os.path.join(IMAGE_DIR, "%s-rootfs.tar.gz" % osname)

    if os.path.exists(rootfile):
        return rootfile

    rawfile = None
    if file.endswith(".tar.gz"):
        rawname = None
        with tarfile.open(file) as tar:
            for n in tar:
                rawname = n.name
                break
        rawfile = os.path.join(DOWNLOAD_DIR, rawname)
        if not os.path.exists(rawfile):
            subprocess.run(["tar", "xvf", file], cwd=DOWNLOAD_DIR)
        else:
            print("using already unpacked image")

    if file.endswith(".raw.xz"):
        rawfile = os.path.join(DOWNLOAD_DIR, file[:-3])
        if not os.path.exists(rawfile):
            subprocess.run(["unxz", file], cwd=DOWNLOAD_DIR)
        else:
            print("using already unpacked image")

    if file.endswith(".qcow2"):
        rawfile = os.path.join(DOWNLOAD_DIR, "%s.raw" % file[:-6], )
        if not os.path.exists(rawfile):
            subprocess.run(["qemu-img", "convert", file, rawfile], cwd=DOWNLOAD_DIR)
        else:
            print("using already unpacked image")

    if file.endswith(".raw"):
        rawfile = file
    #return rawfile
    if rawfile is None:
        print("could not handle image")
        sys.exit(1)

    proc = subprocess.Popen(["fdisk","-l",rawfile], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    fdisk_output, fdisk_error = proc.communicate()
    fdisk_output = fdisk_output.decode(sys.stdout.encoding)

    start = list(parse_fdisk(fdisk_output).items())[0][1]["start"]*512

    if not os.path.exists(IMAGE_DIR):
        os.makedirs(IMAGE_DIR)


    if not os.path.exists(rootfile):
        mntdir = os.path.join(BASE_DIR,"mnt")
        if not os.path.exists(mntdir):
            os.makedirs(mntdir)
            subprocess.run(["sudo","mount","-o","ro,loop,offset=%d"%start,rawfile,mntdir])
            files = os.listdir(mntdir)
            print(files)
            subprocess.run(["sudo","tar","czf",rootfile,*files],cwd=mntdir)
            subprocess.run(["sudo", "umount", mntdir])
            os.rmdir(mntdir)
        else:
            print("please check your mnt dir")
            sys.exit(1)
    else:
        print("use existing rootfs.tar")

    return rootfile

def make_meta(conf):

    metafile = os.path.join(IMAGE_DIR, "%s-%s-metadata.tar.gz" % (conf["distribution"], conf["release"]))
    if not os.path.exists(metafile):
        context = {}
        context.update(conf)
        context["date"] = datetime.now().strftime("%Y%m%d")
        context["timestamp"] = int(datetime.now().strftime("%s"))

        with open(os.path.join(BASE_DIR,"templates","metadata.yaml")) as r:
            template = Template(r.read())
            str = template.render(**context)

        mddir = os.path.join(BASE_DIR,"metadata")
        with open(os.path.join(mddir,"metadata.yaml"),"w") as f:
            f.write(str)

        files = os.listdir(mddir)
        print(files)
        subprocess.run(["tar", "czf", metafile, *files], cwd=mddir)
