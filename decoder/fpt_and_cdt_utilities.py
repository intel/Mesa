# Copyright (c) 2020 Intel Corporation. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sub license, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice (including the
# next paragraph) shall be included in all copies or substantial portions
# of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT.
# IN NO EVENT SHALL PRECISION INSIGHT AND/OR ITS SUPPLIERS BE LIABLE FOR
# ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#


import struct
import bitstring


class CodePartitionDescriptor:
    """
    This is container to hold the information gotten from entries in the Code Partition entries in the binary file that
        is the entire CSME.
        The offset of the "table" for this code partition can be computed from the offset location of the
        header (offset_of_cdt_header).  This offset is relative from the start of the overall *FILE* (that was
        given as input at the beginning of the execution chain of the decoder)
        The 'size' is important in sanity checking to not read past the end of the
        code partition
    """
    def __init__(self, offset_of_cdt_header: int, size: int, name: str):
        self.offset_of_cdt_header = offset_of_cdt_header
        self.size = size
        self.name = name

    def __str__(self):
        return ("code partition '{0}', {1} bytes in size, located at 0x{2:08x} "
                "({2} bytes from start of file)".format(self.name, self.size, self.offset_of_cdt_header,
                                                        self.offset_of_cdt_header))


def string_from_buffer(buffer, string_size: int, offset: int = 0):
    """
    :param buffer: bytes returned from e.g. file.read(), which needs to be at least length of string_size+offset
    :param string_size: the length of the expected string to extract from the buffer
    :param offset: where in buffer, to start the string extraction, expressed as bytes from start of buffer
    :return: a UTF-8 string, if decoding was successful. None, otherwise

    This function is a convenience wrapper around struct.unpack_from(), which formats the 'unpack parameter string'
    correctly and checks the return of unpack_from, and digs out the string from the return of unpack_from
    """

    strbytes = struct.unpack_from(str(string_size) + 's', buffer, offset)
    if len(strbytes) != 1:
        return None
    return strbytes[0].decode("UTF-8")


def bitstream_from_file_fqpn(file_input_fqpn: str, begin_at_offset_in_bytes: int = 0):
    """
    :param file_input_fqpn: the fully qualified path and name of the file that contains CSME code binaries
                        (i.e. the input file provided by the user on the command line)
    :param begin_at_offset_in_bytes: where to fast-forward seek to in the file before attempting a search

    :return: a bitstring.ConstBitStream of the specified file's data, cued to the specified offset location
    """
    return bitstring.ConstBitStream(filename=file_input_fqpn, offset=begin_at_offset_in_bytes * 8)


def bitstream_from_file_object(file_input, begin_at_offset_in_bytes: int = 0):
    """
    :param file_input: opened file that contains CSME code binaries
                            (i.e. the input file provided by the user on the command line)
    :param begin_at_offset_in_bytes: where to fast-forward seek to in the file before attempting a search
    :return: a bitstring.ConstBitStream of the specified file's data, cued to the specified offset location
    """
    return bitstring.ConstBitStream(file_input, offset=begin_at_offset_in_bytes * 8)


def find_fpt_in_file_fqpn(file_input_fqpn: str, begin_at_offset_in_bytes: int = 0):
    """

    :param file_input_fqpn: the fully qualified path and name of the file that contains CSME code binaries
                            (i.e. the input file provided by the user on the command line)
    :param begin_at_offset_in_bytes: where to fast-forward seek to in the file before attempting a search
    :return: an integer representing the offset in the file where a File Partition Table resides, if one was found
        (this offset is the byte at which the '$' in '$FPT' is located)
        None, if no FPT was found

    The FPT can be located at a location other than 0 in a CSME image file; sometimes varies by packaging tool build
        version. This function is a convenience and a debugging tool to locate the position at which routines that
        parse the FPT should start reading.
    """

    s = bitstream_from_file_fqpn(file_input_fqpn, begin_at_offset_in_bytes)
    return find_fpt(s, begin_at_offset_in_bytes)


def find_fpt_in_opened_file(file_object, begin_at_offset_in_bytes: int = 0):
    """
    :param file_object: opened file that contains CSME code binaries
                            (i.e. the input file provided by the user on the command line)
    :param begin_at_offset_in_bytes: where to fast-forward seek to in the file before attempting a search
    :return:  an integer representing the offset in the file where a File Partition Table resides, if one was found
        (this offset is the byte at which the '$' in '$FPT' is located)
        None, if no FPT was found

    The FPT can be located at a location other than 0 in a CSME image file; sometimes varies by packaging tool build
        version. This function is a convenience and a debugging tool to locate the position at which routines that
        parse the FPT should start reading.
    """
    s = bitstream_from_file_object(file_object, begin_at_offset_in_bytes)
    return find_fpt(s, begin_at_offset_in_bytes)


def find_fpt(data_bits: bitstring.ConstBitStream, begin_at_offset_in_bytes: int = 0):
    """
    Scan the bitstream looking for a Magic Number (see code below) that identifies a File Table.
    Return the position of the file table (needed for further descent into the file structures) and some
        other info (versions and number of entries)
    :param data_bits: a BitStream object representing the input (generally constructed from the input specified to the
        decoder, like a file.  e.g. look at the function 'find_fpt_in_opened_file'
    :param begin_at_offset_in_bytes: from where in the input the BitStream was constructed. This is NOT necessary for
        correct operation; it is a convenience so that the return value will already have computed the location
        relative to the start of the input file (but if the caller wishes, it can do this addition/offsetting itself,
        and just leave the default 0 value for the parameter)
    :return: a list of values: [0] = the location in the bitstream where the Magic Number for the File Table was found
        (* the exact meaning of the "location" depends on begin_at_offset_in_bytes and the bitstream that was passed in;
        see above)
        [1] = the number of entries (code partition directories) in this file
        [2] = the header version; this varies from CSME version to version
        [3] = the version of the code p. directories. Again, this varies...
    """
    f = data_bits.find('0x24465054', bytealigned=True)  # look for the string '$FPT' (expressed in hex, here)
    if f:
        # grab the number of entries, the header version and entry version, to return (this helps the human interpreting
        #   the result in figuring out if this is a valid FPT)
        fpt_tag, num_entries, header_version, entry_version = data_bits.readlist('hex:32, uintle:32, uint:8, uint:8')
        return [begin_at_offset_in_bytes + int(f[0] / 8), num_entries, header_version, entry_version]
    return None


def get_all_cdt(from_opened_file, offset_of_fpt: int, debug_prints=False):
    """
    :param from_opened_file: an opened file handle; e.g. from open(filename,...). It does not have to be cue'd to any
                        particular location, as this function will seek() to where it needs to go
    :param offset_of_fpt: the location in the file where an FPT resides (e.g. the return value of find_fpt_in_file() )
    :param debug_prints: (optional) set to True for debug prinouts to stdout
    :return: on success: a list of CodePartitionDescriptor objects describing code (partition) directory tables (CDT)
        otherwise: None  (if there was no FPT at the given location, or there were no code partitions defined in the FPT

    Side effect:
        the file handle from_opened_file will be altered and will point to a different location after the call completes

    Code partitions, and code partition directories, are where the CSME binary objects are stored. They are indexed
        as entries in the FPT with offsets within the same input file where the FPT is found. This function does a few
        'sanity' checks on the CDT entry to see if it's valid, though these are nowhere near definitive or conclusive
        (it'll catch only significant corruption). (TODO: checksum checking is possible here)
    """

    from_opened_file.seek(offset_of_fpt)
    # FPT header is first; it's 32 bytes; of interest are the number of entries
    # This is at byte 4 from the start of the header. The "entry version" is ignored
    # ...but since the FPT is small enough, the whole thing is read in here to a buffer (makes it faster to add things
    # to this code later on, for processing other parts of the header, extra checks, etc.)

    fpt_buffer = from_opened_file.read(32)
    # do a very cursory check to see if it's a legal FPT structure; header marker (@ offset 0) == "$FPT"
    header_check = string_from_buffer(fpt_buffer, 4)
    if header_check != '$FPT':
        print("Not a valid FPT at position 0x{0:08x} ({0})".format(
            offset_of_fpt))
        return None

    num_of_entries = struct.unpack_from('<I', fpt_buffer, 4)[0]

    code_partitions = []
    for entry_index in range(0, num_of_entries):
        fpte_buffer = from_opened_file.read(32)
        # check to see if it's both valid AND a code partition type; this is in the u32 starting at byte 28 (bit 224),
        # bits [0-6] partition type (0 for code), and bits [24-31] ( 0xFF means invalid)
        raw_u32 = struct.unpack_from("<I", fpte_buffer, 28)[0]
        ptype = raw_u32 & 0x7F
        if ptype != 0:
            if debug_prints:
                print("FPT entry at index {0} is not a 'code type' (value was: {1}). Skipping.".format(
                    entry_index, ptype))
            continue
        is_invalid = (raw_u32 >> 24) & 0xFF
        if is_invalid == 0xFF:
            if debug_prints:
                print("FPT entry at index {0} is marked Invalid (value was: {1}). Skipping.".format(
                    entry_index, is_invalid))
            continue
        # otherwise, it's a valid code partition entry
        cdt_offset = struct.unpack_from('<I', fpte_buffer, 8)[0]
        cdt_size = struct.unpack_from('<I', fpte_buffer, 12)[0]
        cdt_name = string_from_buffer(fpte_buffer, 4)
        if cdt_name is None:
            cdt_name = ""
        else:
            cdt_name = cdt_name.strip()
            cdt_name = cdt_name.strip('\0')
        if debug_prints:
            print("Found valid code partition named {0}, {1} bytes in size, that is located at 0x{2:08x} "
                  "({2} bytes from start of file)".format(cdt_name, cdt_size, cdt_offset, cdt_offset))
        code_partitions.append(CodePartitionDescriptor(cdt_offset, cdt_size, cdt_name))

    return None if len(code_partitions) == 0 else code_partitions


class CodeObjectEntry:

    def __init__(self, in_partition: CodePartitionDescriptor, rel_offset_of_data_in_partition: int, size: int,
                 name: str, is_huffman_compressed: bool):
        """
        :param in_partition: a reference to the CodePartitionDescriptor object for the code partition/dir. that this
            code object belongs to; needed because the offset given here is *relative* and must be used with the
            (absolute) offset within the in_partition object
        :param rel_offset_of_data_in_partition: relative location (relative to the start of the code partition)
            of the encoded data for this code object
        :param size: if is_huffman_compressed == True, then this is the DECODED (expected target size in output) of the
            Huffman compressed binary.  (see the decoder functionality in csme_unpack.py for how this is used)
            (* this code base does NOT handle the case where code objects are not Huffman compressed)
        """

        self.in_partition = in_partition
        self.rel_offset_of_data_in_partition = rel_offset_of_data_in_partition
        self.size = size
        self.name = name
        self.is_huffman_compressed = is_huffman_compressed

    def getsize(self):
        return self.size

    def getoffset(self):
        return self.rel_offset_of_data_in_partition

    def getname(self):
        return self.name

    def getishuffmancompressed(self):
        return self.is_huffman_compressed

    def __str__(self):
        return ("code object " + self.name + " is at {0}, size value of {1} and "
                .format(self.rel_offset_of_data_in_partition, self.size)
                + ("is" if self.is_huffman_compressed else "is NOT") +
                " huffman compressed")

    def as_csv_str(self):
        return (self.name + ",{0},{1},"
                .format(self.rel_offset_of_data_in_partition, self.size)
                + ("True" if self.is_huffman_compressed else "False")
                )


def get_code_objects_in_code_partition(from_opened_file, code_partition_desc: CodePartitionDescriptor,
                                       debug_prints=False):
    """
    :param from_opened_file: an opened file handle; e.g. from open(filename,...). It does not have to be cue'd to any
                            particular location, as this function will seek() to where it needs to go
    :param code_partition_desc: an object describing the code partition/directory (such as its location, size, and name)
    :param debug_prints: (optional) set to True for debug prinouts to stdout
    :return: on success: a list of CodeObjectEntry objects describing binaries within the code partition/directory
        otherwise: None  (if no code objects could be found in this code directory)

    Side effect:
        the file handle from_opened_file will be altered and will point to a different location after the call completes

    This function parses the CDT and finds all the entries which describe code objects; the actual binaries
    (NOTE: These Are The Droids You're Looking For(c)...these are the actual CSME binary objects, like the 'kernel',
        drivers, etc...that make up the CSME runtime.)
    Their description is most importantly their location relative to the CDT, their size, and the nature of
        the compression (Huffman encoded or not)
    TODO: this function does zero error checking, and any misread/misalignment (e.g. wrong offset to CDT given) will
        result in an incorrect CodeObjectEntry that will point to some random location in the file. This error will
        only be evident when the actual decompression/decoding of that binary fails (which makes it hard to trace back
        to the fact that this was the origin of that error)
    """
    from_opened_file.seek(code_partition_desc.offset_of_cdt_header)
    # CPD Header is here. Unfortunately, it can either be 16 bytes or 20 bytes in size; determinant: the 10th byte
    #   (called "header_length"; straightforward value)
    # read first 11 bytes
    cpd_header = bytearray(from_opened_file.read(11))
    header_length = struct.unpack_from('B', cpd_header, 10)[0]
    # and append the rest of the header to the buffer
    cpd_header.extend(from_opened_file.read(header_length - 11))
    num_code_objects = struct.unpack_from('<I', cpd_header, 4)[0]
    if debug_prints:
        print("there are {0} code objects in this partition".format(num_code_objects))

    code_objects = []
    for entry_index in range(0, num_code_objects):
        entry_bytes = from_opened_file.read(24)
        # name is the first 12 bytes
        code_obj_name = string_from_buffer(entry_bytes, 12)
        if code_obj_name is None:
            code_obj_name = ""
        else:
            code_obj_name = code_obj_name.strip()
            code_obj_name = code_obj_name.strip('\0')

        # next, at byte offset 12 (bit offset 96) is a packed u32, as follows:
        # offset             : 25  (bits 0-24)  // This is the offset from the beginning of the code partition
        # huffman_compressed : 1   (25)         // Huffman compressed Y/N (1/0)
        # reserved           : 6   (26-31)      // all set to 0
        raw_u32 = int(struct.unpack_from("<I", entry_bytes, 12)[0])
        rel_offset_of_code_object = raw_u32 & 0x1FFFFFF
        is_huffman_compressed = (raw_u32 & 0x2000000) != 0

        # next, at byte offset 16 is a special value related to the size of the code object;
        # For Huffman-compressed modules, this refers to the uncompressed size in bytes.
        # For software-compressed modules, this refers to the compressed size in bytes
        code_obj_size = struct.unpack_from("<I", entry_bytes, 16)[0]

        code_object = CodeObjectEntry(code_partition_desc, rel_offset_of_code_object,
                                      code_obj_size, code_obj_name, is_huffman_compressed)
        if debug_prints:
            print(code_object)

        code_objects.append(code_object)

    return None if len(code_objects) == 0 else code_objects


def get_huffman_compressed_code_objects_in_code_partition(from_opened_file,
                                                          code_partition_desc: CodePartitionDescriptor,
                                                          debug_prints=False):
    """
    :param from_opened_file: an opened file handle; e.g. from open(filename,...). It does not have to be cue'd to any
                        particular location, as this function will seek() to where it needs to go
    :param code_partition_desc: an object describing the code partition/directory (such as its location, size, and name)
    :param debug_prints: (optional) set to True for debug prinouts to stdout
    :return: on success: an list of CodeObjectEntry objects describing binaries within the code partition/directory;
                    ONLY objects that were Huffman encoded/compressed will be in the list
            otherwise: None  (if no code objects could be found in this code directory)

    Side effect:
        the file handle from_opened_file will be altered and will point to a different location after the call completes

    This is a wrapper on get_code_objects_in_code_partition() which just filters out from its return, all list elements
        (CodeObjectEntry-ies) which indicate that the code binary is Huffman encoded/compressed.
    NOTE: Implemented as a very quick and dirty "filter"; not claimed or intended to be particularly efficient, it
        exists solely for convenience and making the rest of the reference code clearer
    """

    code_objects = get_code_objects_in_code_partition(from_opened_file, code_partition_desc, False)
    if code_objects is None:
        return None
    index = 0
    while index < len(code_objects):
        if not code_objects[index].is_huffman_compressed:
            del (code_objects[index])
        else:
            index += 1
    if debug_prints:
        print("Filtered list on Huffman coding:")
        for code_object in code_objects:
            print(code_object)

    return code_objects
