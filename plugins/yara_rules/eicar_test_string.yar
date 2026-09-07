/*
 * Detects the EICAR Anti-Virus Test File string -- a real, standardized,
 * publicly documented test signature (https://www.eicar.org/), not a
 * malware detection. It exists so this rules directory has ONE verifiable,
 * safe, working example instead of a fabricated "detects real malware"
 * rule this project cannot honestly stand behind. Add your own vetted
 * .yar rules (e.g. from an internal source, or reviewed community rules)
 * to this directory -- plugin 34 loads every *.yar file here.
 */
rule EICAR_Test_String
{
    meta:
        description = "Matches the standard EICAR AV test string, not real malware"
        reference = "https://www.eicar.org/download-anti-malware-testfile/"

    strings:
        $eicar = "X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

    condition:
        $eicar
}
