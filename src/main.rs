#![doc = include_str!("../README.md")]

use std::fmt::Write as FmtWrite;
use std::fs::metadata;
use std::io::{Error, ErrorKind, Write as IoWrite};
#[cfg(target_os = "linux")]
use std::os::linux::fs::MetadataExt;
#[cfg(target_os = "macos")]
use std::os::macos::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::process::Command;

use arrrg::CommandLine;
use sha2::{Digest, Sha256};

const SCRIPT: &'static str = r#"#!/bin/sh

set -e

DEFTSILO_ROOT=`dirname $0`
if test "x${DEFTSILO_ROOT}" = x;
then
    DEFTSILO_ROOT=.
fi
DEFTSILO_ROOT=`realpath -q ${DEFTSILO_ROOT}`
DEFTSILO_INSTALL=deftsilo_cp

while getopts "l" arg
do
    case "$1" in
    -l)
        echo "linking, not copying"
        DEFTSILO_INSTALL=deftsilo_ln
        shift
        ;;
    --)
        shift
        break
        ;;
    esac
done

DEFTSILO_TARGET="$1"
shift

deftsilo_err_exit() {
    echo $*
    exit 1
}

deftsilo_sha256() {
    sha256sum "$1" | awk '{print $1}'
}

deftsilo_mkdir() {
    d="$1"
    shift
    m="$1"
    shift
    dest="${DEFTSILO_TARGET}/$d"
    if test -f "$dest"; then
        deftsilo_err_exit cannot mkdir '"'$dest'"': would clobber a file
    elif test '!' -e "$dest"; then
        mkdir "$dest"
    fi
    if test -d "$dest"; then
        chmod $m "$dest"
    fi
}

deftsilo_cp() {
    f="$1"
    shift
    m="$1"
    shift
    dest="${DEFTSILO_TARGET}/$f"
    if test -d "$dest"; then
        deftsilo_err_exit cannot copy "$dest": would clobber a directory
    elif test '!' -f "$dest"; then
        cp "${DEFTSILO_ROOT}/$f" "$dest"
        chmod "$m" "$dest"
    else
        exp=`deftsilo_sha256 "$dest"`
        found=no
        for hash in $@
        do
            if test x"$exp" = x"$hash"; then
                cp "${DEFTSILO_ROOT}/$f" "$dest"
                chmod "$m" "$dest"
                found=yes
            fi
        done
        if test x"$found" = xno; then
            deftsilo_err_exit failed to copy "$f": unsaved changes
        fi
    fi
}

deftsilo_ln() {
    f="$1"
    shift
    m="$1"
    shift
    dest="${DEFTSILO_TARGET}/$f"
    if test -d "$dest"; then
        deftsilo_err_exit cannot link "$dest": would clobber a directory
    elif test -L "$dest"; then
        true
    elif test -f "$dest"; then
        exp=`deftsilo_sha256 "$dest"`
        found=no
        for hash in $@
        do
            if test x"$exp" = x"$hash"; then
                unlink "$dest"
                ln -s "${DEFTSILO_ROOT}/$f" "$dest"
                found=yes
            fi
        done
        if test x"$found" = xno; then
            deftsilo_err_exit failed to link "$f": unsaved changes
        fi
    elif test '!' -L "$dest"; then
        ln -s "${DEFTSILO_ROOT}/$f" "$dest"
    fi
}

deftsilo_install() {
    "$DEFTSILO_INSTALL" $@
}

"#;

const TESTS: &'static str = r#"
deftsilo_err_exit() {
    DEFTSILO_ERROR="$*"
}

deftsilo_mode() {
    ls -ld $1 | awk '{ print $1 }'
}

set -x

# Test setup
TESTING_ROOT=`mktemp -d`
DEFTSILO_ROOT="${TESTING_ROOT}/dotfiles"
DEFTSILO_TARGET="${TESTING_ROOT}/target"
mkdir -p "${DEFTSILO_ROOT}"
mkdir -p "${DEFTSILO_TARGET}"

# Test 1:  Does deftsilo_sha256 return a valid checksum?
echo "this is a test file" > "${DEFTSILO_ROOT}/file1"

EXPECTED_SHA256="b6668cf8c46c7075e18215d922e7812ca082fa6cc34668d00a6c20aee4551fb6"
RETURNED_SHA256=`deftsilo_sha256 "${DEFTSILO_ROOT}/file1"`
if test "x$EXPECTED_SHA256" != "x$RETURNED_SHA256"
then
    echo sha256 does not work on this platform
    exit 1
fi

# Test 2:  Does mkdir succeed in creating a directory under the target?
DEFTSILO_ERROR=""
deftsilo_mkdir dir1 777
if test "x$DEFTSILO_ERROR" != x
then
    echo mkdir does not work on this platform
    exit 2
fi
if ! test -d "${DEFTSILO_TARGET}/dir1"
then
    echo mkdir did not make a directory
    exit 2
fi

# Test 3:  Does mkdir succeed if the file already exists?
DEFTSILO_ERROR=""
deftsilo_mkdir dir1 777
if test "x$DEFTSILO_ERROR" != x
then
    echo mkdir does not work on this platform
    exit 3
fi
if ! test -d "${DEFTSILO_TARGET}/dir1"
then
    echo mkdir did not make a directory
    exit 3
fi
OBSERVED_MODE=`deftsilo_mode "${DEFTSILO_TARGET}/dir1"`
if test x"${OBSERVED_MODE}" != xdrwxrwxrwx
then
    echo mkdir did not chmod the directory
    exit 3
fi

# Test 4:  Does mkdir update the directory mode when directory exists?
DEFTSILO_ERROR=""
deftsilo_mkdir dir1 755
if test "x$DEFTSILO_ERROR" != x
then
    echo mkdir does not work on this platform
    exit 4
fi
if ! test -d "${DEFTSILO_TARGET}/dir1"
then
    echo mkdir did not make a directory
    exit 4
fi
OBSERVED_MODE=`deftsilo_mode "${DEFTSILO_TARGET}/dir1"`
if test x"${OBSERVED_MODE}" != xdrwxr-xr-x
then
    echo mkdir did not chmod the directory
    exit 4
fi

# Test 5:  Does mkdir fail when trying to create a directory name that's already in use as a file?
DEFTSILO_ERROR=""
cp "${DEFTSILO_ROOT}/file1" "${DEFTSILO_TARGET}/file1"
deftsilo_mkdir file1 750
if test "x$DEFTSILO_ERROR" != x'cannot mkdir "'"${DEFTSILO_TARGET}"'/file1": would clobber a file'
then
    echo mkdir does not work on this platform
    exit 5
fi

# Test 6:  Does cp copy a file that doesn't yet exist?
DEFTSILO_ERROR=""
cp "${DEFTSILO_ROOT}/file1" "${DEFTSILO_ROOT}/file6"
deftsilo_cp file6 750
if test "x$DEFTSILO_ERROR" != x
then
    echo cp does not work on this platform
    exit 6
fi
if ! test -f "${DEFTSILO_TARGET}/file6"
then
    echo cp did not copy a file
    exit 6
fi
OBSERVED_MODE=`deftsilo_mode "${DEFTSILO_TARGET}/file6"`
if test x"${OBSERVED_MODE}" != x-rwxr-x---
then
    echo cp did not chmod a file
    exit 6
fi

# Test 7:  Does cp copy a file if the hash matches?
DEFTSILO_ERROR=""
deftsilo_cp file6 777 b6668cf8c46c7075e18215d922e7812ca082fa6cc34668d00a6c20aee4551fb6
if test "x$DEFTSILO_ERROR" != x
then
    echo cp does not work on this platform
    exit 7
fi
if ! test -f "${DEFTSILO_TARGET}/file6"
then
    echo cp did not copy a file
    exit 7
fi
OBSERVED_MODE=`deftsilo_mode "${DEFTSILO_TARGET}/file6"`
if test x"${OBSERVED_MODE}" != x-rwxrwxrwx
then
    echo cp did not chmod a file
    exit 7
fi

# Test 8:  Does cp copy a file if the hash fails to match?
DEFTSILO_ERROR=""
deftsilo_cp file6 700
if test "x$DEFTSILO_ERROR" != "xfailed to copy file6: unsaved changes"
then
    echo cp does not work on this platform
    exit 8
fi
OBSERVED_MODE=`deftsilo_mode "${DEFTSILO_TARGET}/file6"`
if test x"${OBSERVED_MODE}" != x-rwxrwxrwx
then
    echo cp chmoded a file when it should not
    exit 8
fi

# Test 9:  Does cp fail to copy a file if it's already a directory?
DEFTSILO_ERROR=""
echo 'test 9 checks that files do not stomp directories' > "${DEFTSILO_ROOT}/test9"
mkdir "${DEFTSILO_TARGET}/test9"
deftsilo_cp test9 700
if test "x$DEFTSILO_ERROR" != "xcannot copy ${DEFTSILO_TARGET}/test9: would clobber a directory"
then
    echo cp moved a file over a directory
    exit 9
fi

# Test 10:  Does ln link a file that doesn't yet exist?
DEFTSILO_ERROR=""
cp "${DEFTSILO_ROOT}/file1" "${DEFTSILO_ROOT}/file10"
deftsilo_ln file10 750
if test "x$DEFTSILO_ERROR" != x
then
    echo ln does not work on this platform
    exit 10
fi
if ! test -L "${DEFTSILO_TARGET}/file10"
then
    echo ln did not copy a file
    exit 10
fi

# Test 11:  Does ln link a file if the hash matches?
DEFTSILO_ERROR=""
deftsilo_ln file10 777 b6668cf8c46c7075e18215d922e7812ca082fa6cc34668d00a6c20aee4551fb6
if test "x$DEFTSILO_ERROR" != x
then
    echo ln does not work on this platform
    exit 11
fi
if ! test -L "${DEFTSILO_TARGET}/file10"
then
    echo ln did not copy a file
    exit 11
fi

# Test 12:  Does ln link a file if the hash fails to match?
DEFTSILO_ERROR=""
echo 'file 12 A' > "${DEFTSILO_ROOT}/file12"
echo 'file 12 B' > "${DEFTSILO_TARGET}/file12"
deftsilo_ln file12 700
if test "x$DEFTSILO_ERROR" != "xfailed to link file12: unsaved changes"
then
    echo ln does not work on this platform
    exit 12
fi

# Test 13:  Does ln fail to link a file if it's already a directory?
DEFTSILO_ERROR=""
echo 'test 13 checks that files do not stomp directories' > "${DEFTSILO_ROOT}/test13"
mkdir "${DEFTSILO_TARGET}/test13"
deftsilo_ln test13 700
if test "x$DEFTSILO_ERROR" != "xcannot link ${DEFTSILO_TARGET}/test13: would clobber a directory"
then
    echo ln moved a file over a directory
    exit 13
fi

echo SUCCESS
"#;

fn to_hexdigest(h: Sha256) -> String {
    let digest = h.finalize();
    let mut hex_digest = String::with_capacity(64);
    for byte in &digest {
        write!(&mut hex_digest, "{:02x}", *byte).expect("should be able to write to string");
    }
    hex_digest
}

fn sha256bytes(s: &[u8]) -> String {
    let mut hasher = Sha256::default();
    hasher.update(s);
    to_hexdigest(hasher)
}

fn history<P: AsRef<Path>>(root: P, relative: &str) -> Result<Vec<String>, Error> {
    let cmd = Command::new("git")
        .args(["whatchanged", "--follow", "--no-abbrev", "--oneline", relative])
        .current_dir(root.as_ref())
        .output()?;
    std::io::stderr().write_all(&cmd.stderr)?;
    if !cmd.status.success() {
        return Err(Error::new(ErrorKind::Other, format!("child exited {}", cmd.status)));
    }
    let stdout: String = String::from_utf8(cmd.stdout).map_err(Error::other)?;
    let lines: Vec<String> = stdout.split('\n').map(String::from).collect();
    let mut digests: Vec<String> = vec![];
    for line in lines.into_iter() {
        if !line.starts_with(':') {
            continue;
        }
        let pieces: Vec<&str> = line.split(' ').collect();
        if pieces.len() < 4 {
            continue;
        }
        let r#ref = pieces[3];
        if r#ref == "0000000000000000000000000000000000000000" {
            continue;
        }
        let cmd = Command::new("git")
            .args(["cat-file", "blob", r#ref])
            .current_dir(root.as_ref())
            .output()?;
        std::io::stderr().write_all(&cmd.stderr)?;
        if !cmd.status.success() {
            return Err(Error::new(ErrorKind::Other, format!("child exited {}", cmd.status)));
        }
        let hexdigest = sha256bytes(&cmd.stdout);
        digests.push(hexdigest);
    }
    Ok(digests)
}

fn get_mode<P1: AsRef<Path>, P2: AsRef<Path>>(root: P1, path: P2) -> Result<u32, Error> {
    let md = metadata(root.as_ref().to_path_buf().join(path.as_ref()))?;
    Ok(md.st_mode() & 0o777)
}

fn path_to_string<P: AsRef<Path>>(path: P) -> Result<String, Error> {
    let path_str: String = path.as_ref().to_string_lossy().to_string();
    if PathBuf::from(&path_str) != path.as_ref() {
        Err(Error::other("path contains invalid UTF-8"))
    } else {
        Ok(path_str)
    }
}

fn quoted_path<P: AsRef<Path>>(path: P) -> Result<String, Error> {
    let path_str: String = path_to_string(path)?;
    if path_str.chars().any(|c| c == '"' || c.is_ascii_control()) {
        Err(Error::other("path contains '\"' or an ASCII control-character"))
    } else {
        Ok(format!("\"{}\"", path_str))
    }
}

fn generate_mkdir<P1: AsRef<Path>, P2: AsRef<Path>>(root: P1, directory: P2) -> Result<String, Error> {
    let mode = get_mode(&root, &directory)?;
    Ok(format!("deftsilo_mkdir {} {:o}\n", quoted_path(directory)?, mode))
}

fn generate_install<P1: AsRef<Path>, P2: AsRef<Path>>(root: P1, file: P2, refs: Vec<String>) -> Result<String, Error> {
    let mode = get_mode(&root, &file)?;
    Ok(format!("deftsilo_install {} {:o} {}\n", quoted_path(file)?, mode, refs.join(" ")))
}

fn assemble_paths<P1: AsRef<Path>, P2: AsRef<Path>>(root: P1, path: P2, directories: &mut Vec<PathBuf>, files: &mut Vec<PathBuf>) -> Result<(), Error> {
    let canon = path.as_ref().to_path_buf().canonicalize()?;
    let Ok(relative) = canon.strip_prefix(&root) else {
        return Err(Error::other(format!("{} canonicalizes to outside the provided root", path.as_ref().to_string_lossy())));
    };
    if path.as_ref().is_dir() {
        directories.push(relative.to_path_buf());
        for entry in std::fs::read_dir(path.as_ref())? {
            let entry = entry?;
            let path = entry.path();
            if let Some(file_name) = path.file_name() {
                if file_name == ".git" || file_name == "install.sh" {
                    continue;
                }
            }
            assemble_paths(root.as_ref(), path, directories, files)?;
        }
        Ok(())
    } else if path.as_ref().is_file() {
        files.push(relative.to_path_buf());
        Ok(())
    } else {
        Err(Error::other(format!("{} is not a file or directory", path.as_ref().to_string_lossy())))
    }
}

fn install_sh<P: AsRef<Path>>(root: P) -> Result<String, Error> {
    let mut dirs = vec![];
    let mut files = vec![];
    assemble_paths(&root, &root, &mut dirs, &mut files)?;
    dirs.sort();
    files.sort();
    let mut install_sh = String::from(SCRIPT);
    for dir in dirs.into_iter() {
        if dir.to_string_lossy().len() == 0 {
            continue;
        }
        install_sh += &generate_mkdir(&root, dir)?;
    }
    for file in files.into_iter() {
        let exp = history(&root, &path_to_string(&file)?)?;
        install_sh += &generate_install(&root, file, exp)?;
    }
    Ok(install_sh)
}

#[derive(Eq, PartialEq, arrrg_derive::CommandLine)]
struct Options {
    #[arrrg(flag, "generate the unit tests rather than an install.sh")]
    test: bool,
    #[arrrg(optional, "generate dotfiles from this directory (default: .)")]
    path: String,
}

impl Default for Options {
    fn default() -> Self {
        Self {
            test: false,
            path: ".".to_string(),
        }
    }
}

fn main() {
    let (cmdline, free) = Options::from_command_line("Usage: deftsilo [OPTIONS]");
    if !free.is_empty() {
        eprintln!("command takes no positional arguments");
        std::process::exit(1);
    }
    if !cmdline.test {
        let root = PathBuf::from(cmdline.path).canonicalize().expect("--path should canonicalize");
        println!("{}", install_sh(root).expect("install.sh should generate"));
        println!("echo all files successfully installed");
    } else {
        println!("{}{}", SCRIPT, TESTS.trim());
    }
}
