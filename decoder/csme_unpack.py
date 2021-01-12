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

import argparse
import sys
import bitstring
import os
import binascii

from decoder.fpt_and_cdt_utilities import get_all_cdt, find_fpt_in_file_fqpn, find_fpt_in_opened_file
from decoder.fpt_and_cdt_utilities import get_huffman_compressed_code_objects_in_code_partition
from decoder.fpt_and_cdt_utilities import CodeObjectEntry

huffman_table = {}
longest_huffman_code_in_bits = 0
shortest_huffman_code_in_bits = sys.maxsize

HUFFMAN_PAGE_DECODED_SIZE_MAX = 4096


def clear_huffman_table_data():
    """
    clear the global Huffman table variable and reset the min/max code (size in bits) counter vars
    :return: None
    """
    global huffman_table, shortest_huffman_code_in_bits, longest_huffman_code_in_bits
    huffman_table = {}
    longest_huffman_code_in_bits = 0
    shortest_huffman_code_in_bits = sys.maxsize


def get_longest_huffman_code_in_nbits():
    """
    convenience accessor for the longest code (in number of bits) in the global Huffman table, currently
    :return: longest_huffman_code_in_bits value
    """
    global longest_huffman_code_in_bits
    return longest_huffman_code_in_bits


def get_shortest_huffman_code_in_nbits():
    """
    convenience accessor for the shortest code (in number of bits) in the global Huffman table, currently
    :return: shortest_huffman_code_in_bits value
    """
    global shortest_huffman_code_in_bits
    return shortest_huffman_code_in_bits


def get_huffman_table():
    """
    convenience accessor for the global Huffman table
    :return: the global huffman_table var (a dict., by reference)
    """
    global huffman_table
    return huffman_table


class HuffmanTableEntry:
    """
    A container class which stores each "row" of the parsed Huffman table, in the specific variant that the Intel CSME
    utilizes the tables; that is, for each Huffman code, there are TWO possible "decoded"/"dictionary" values
    (Note that this use of the word "dictionary" has nothing to do with Python's meaning of "dictionary")

    Here are the member vars of the class, with explanation of purpose for each:

    huffman_code: the Huffman code itself; it is stored as-is in an ASCII table representation (as distributed
        with this source code), as a string. e.g. '00011001'
    huffman_code_bits: ...is a converted version of the huffman_code field, to a bitstring BitArray.
        (it is effectively 'cached' in this form, for faster use during the actual decoding process)
    huffman_code_rank:  The length, in bits, of the Huffman code; e.g. '00011001' ---> rank = 8
        It is stored here for convenience in debugging although it isn't strictly necessary, as huffman_code_bits
        has the information explicitly encoded within it (i.e. the BitArray object has a length property)

    dict1_value, dict2_value:  The 2 possible decodings of the Huffman code. They are converted to a bytearray
        (for easy addition into an output bytestream during decoding). Care is taken make sure Python's bytearray
        conversion doesn't flip bytes trying to interpret endianess
    dictionary_data_length:  the 'length' of the dictX_value values, in bytes. It is stored here for convenience in
        debugging although it isn't strictly necessary, as dictX_value vars have the information explictly encoded
        (see the __init__ constructor)

    """
    def __init__(self, dict1: int, dict2: int, dict_data_length_in_bytes: int, rank: int, huffman_code):
        """
        turn both dict(ionary) values from ints into arrays of bytes. the dict_data_length_in_bytes parameter
        tells me how many bytes to have...i.e. how many (if any), 0x00 padding bytes are needed "on the left" side
        e.g. if the dict1 value is 2, then this would plainly be 0x02 as a byte.
        However if dict_data_length_in_bytes == 3, then the result desired is [0x00, 0x00, 0x02] ,
            which is 3 bytes in size
        ===> bytearray() does this, in conjunction with integer.to_bytes(). Use "big"(endian) as the
              parameter to have it not swap bytes around from how they are stores in the table; i.e. convert to bytes
              "literally" and not interpreting it as an "int"
        :param dict1: dict1 value from the Huffman table, as a raw int
        :param dict2: dict2 value from the Huffman table, as a raw int
        :param dict_data_length_in_bytes: how many bytes the dictX values are supposed to expand to (see comments)
        :param rank: the size, in bits of the Huffman code
        :param huffman_code: the Huffman code, as an ASCII string of bits , e.g. '00011001'
        """

        self.dict1_value = bytearray(dict1.to_bytes(dict_data_length_in_bytes, "big"))
        self.dict2_value = bytearray(dict2.to_bytes(dict_data_length_in_bytes, "big"))
        self.dictionary_data_length = dict_data_length_in_bytes
        self.huffman_code_rank = rank
        self.huffman_code = huffman_code
        self.huffman_code_bits = bitstring.ConstBitArray("0b" + str(huffman_code))

    def __str__(self):
        return (str(binascii.hexlify(self.dict1_value)) + " || " + str(binascii.hexlify(self.dict2_value)) + " <== "
                + str(self.huffman_code_bits))


def process_huffman_table_file_line(line: str):
    """
    :param line: a string representing a single line (text terminated by any of the recognized line-terminators
            like \r,\n, etc), from an ASCII version of the Huffman code table
    :return: (none)

    Modifies:
        1. global integers  'longest_huffman_code_in_bits' and 'shortest_huffman_code_in_bits'
        2. global dictionary 'huffman_table'

    The current ASCII versions of the tables have "columns" (whitespace separated values) in the following order:
    Uncompressed Sequence (dict 1)        [0]
    Ref1                                  [1]
    Uncompressed Sequence (dict 2)        [2]
    Ref2                                  [3]
    Length                                [4]
    Depth                                 [5]
    Huffman Code                          [6]

    """

    global longest_huffman_code_in_bits, shortest_huffman_code_in_bits, huffman_table
    tokens = line.split()
    try:
        dict1 = int(tokens[0], 16)
        dict2 = int(tokens[2], 16)
        dlen = int(tokens[4], 10)
        rank = int(tokens[5], 10)
        huffman_code = tokens[6]
        if rank > longest_huffman_code_in_bits:
            longest_huffman_code_in_bits = rank
        if rank < shortest_huffman_code_in_bits:
            shortest_huffman_code_in_bits = rank
    except:
        # non-fatal usually; most likely it hit some initial descriptive lines at the top of the file, or comments, etc
        # return out to the table file reader to move to the next line, ignoring this one
        return
    table_entry = HuffmanTableEntry(dict1, dict2, dlen, rank, huffman_code)
    huffman_table[table_entry.huffman_code_bits] = table_entry


def read_ascii_huffman_table_from_file(file_fqpn: str):
    """
    Simple wrapper on process_huffman_table_file_line() that takes a file path as a string parameter
    :param file_fqpn: the fully-qualified path and filename of the Huffman table (in the ASCII format described in
        comments of process_huffman_table_file_line() )
    :return: None

    Side effect / Modifies: modifies the global Huffman table dictionary var
    """

    f = open(file_fqpn, "r")
    for line in f:
        process_huffman_table_file_line(line)
    f.close()


class LUTentry:
    """
    A container for the LookUp Table entries, parsed from either the standalone LUT files (that accompany "standalone"
        binaries) or from the LUT "sections" in single CSME deployment binaries (e.g. flashable versions in official
        releases)

    Each object of this class represents an entry in the lookup table, which itself represents a "Page" (or plainly,
        a section) of a compressed CSME code object...and thus represents a page of the resulting, decompressed
        code object.

    see the commens in the __init__ constructor about the meaning and relevance of the member vars
    """
    def __init__(self, offset, dictionary_selector):
        """
        :param offset: the offset into the compressed file where this particular compressed page starts.
            THIS IS RELATIVE TO EITHER...
            (1) the start of the standalone file, if it was a standalone LUT file
            (2) the end of the LUT section in a "big, single" CSME binary
        :param dictionary_selector: either 0 or 1, where 0 selects "dict1" value in the HuffmanTableEntry,
            and 1 selects "dict2".  (see class HuffmanTableEntry for explanation of the two values)

        'size' isn't really important, and is calculated (and retroactively assigned to this object) when the
            LUT is parsed (e.g. in read_lut() ).  It is mostly for sanity checking and meaningful output when
            decoding (and debugging)
        """
        self.offset = offset
        self.dictionary_selector = dictionary_selector
        self.size = 0

    def __str__(self):
        return ('Offset= 0x{0:08x}'.format(self.offset) + " , size= {0}".format('?' if self.size == 0 else self.size)
                + " , dictionary selector= " + str(self.dictionary_selector))


def read_lut_file(file_fqpn: str, reverse_byte_ordering=False):
    """
    :param file_fqpn:    the fully-qualified-path-and-name (fqpn) of the file containing the (page) lookup table
    :param reverse_byte_ordering:  treat LUT entries in reverse byte order than normal (Needed due to quirks in certain
                            formats of the input file, such as the "flashable binary")
    :return: the (L)ook(U)p (T)able...a list of LUTentry objects representing the pages of input data in an input file
        of compressed data. The entries are listed in ascending numeric order of offset (bytes into the input file)
    """

    f = open(file_fqpn, "rb")
    f.seek(0, os.SEEK_END)  # seek to end
    total_file_bytes = f.tell()
    f.seek(0, os.SEEK_SET)
    return read_lut(f, total_file_bytes, reverse_byte_ordering)


def read_lut(from_opened_input_file, bytes_of_lut_to_read: int, reverse_byte_ordering=False):
    """
   :param from_opened_input_file:  file handle to the LUT file, positioned at the beginning of the file
   :param bytes_of_lut_to_read:  how many bytes to read; this is a product of the number of entries (4 bytes per)
   :param reverse_byte_ordering:  treat LUT entries in reverse byte order than normal (Needed due to quirks in
                            certain formats of the input file, such as the "flashable binary")

   :return: the (L)ook(U)p (T)able...a list of LUTentry objects representing the pages of input data in an
        input file of compressed data. The entries are listed in ascending numeric order of offset
        (bytes into the input file)
    """
    local_lut_return_value = []
    position = 0
    entry_index = 0
    # !! EC
    while position < bytes_of_lut_to_read:
        # read 4 bytes at a time
        rawdata = from_opened_input_file.read(4)
        position += 4
        huffman_selector = rawdata[(3 if reverse_byte_ordering else 0)] & 0xC0
        if (huffman_selector != 0xC0) and (huffman_selector != 0x40):
            print("lut table entry doesn't have valid huffman selector bits at file offset " + str(position)
                  + " ; skipping 4 bytes ahead")
            continue
        huffman_selector = 1 if (huffman_selector == 0xC0) else 0
        offset = (((rawdata[(3 if reverse_byte_ordering else 0)] & 0x3F) & 0xFF) << 24) \
                 | (((rawdata[(2 if reverse_byte_ordering else 1)]) & 0xFF) << 16) \
                 | (((rawdata[(1 if reverse_byte_ordering else 2)]) & 0xFF) << 8) \
                 | ((rawdata[(0 if reverse_byte_ordering else 3)]) & 0xFF)

        new_lut_entry = LUTentry(offset, huffman_selector)
        if entry_index > 0:
            local_lut_return_value[entry_index - 1].size = new_lut_entry.offset \
                                                           - local_lut_return_value[entry_index - 1].offset
        local_lut_return_value.append(new_lut_entry)
        entry_index += 1

    return local_lut_return_value


def read_lut_of_code_object(from_opened_input_file, target_code_object_entry: CodeObjectEntry, debug_prints=False):
    """
    :param from_opened_input_file: file handle (opened for reading binary) to the CSME binary input file;
                                    does not need to point to any particular location; this function will seek()
    :param target_code_object_entry: the code object descriptor for the specific CSME module binary
                                    (within the input file) that is to be decoded
    :param debug_prints: if True, will dump diagnostic stuff to the console as it runs

    :return: if successful: a list of LUTentry objects for the binary to be decoded, otherwise: None

    Side effect:
        the 'from_opened_input_file' handle will be advanced to the end of the LUT (unless there is an error).
        (it is therefore likely different/at a different position in the caller func. than it was
        prior to this function being called)
    """
    if not target_code_object_entry.is_huffman_compressed:
        # this only applies to Huffman compressed binary blocks
        if debug_prints:
            print("Error: read_lut_of_code_object only works on Huffman compressed binary blocks")
        return None

    # seek to the right location in the file
    from_opened_input_file.seek(target_code_object_entry.in_partition.offset_of_cdt_header
                                + target_code_object_entry.rel_offset_of_data_in_partition, 0)  # 0 == start of file

    if debug_prints:
        print("read_lut_of_code_object(): the lut of the code object named {0} begins at {1} bytes from start of file"
              .format(target_code_object_entry.name, from_opened_input_file.tell()))

    # number of pages will be target_code_object_entry.size / HUFFMAN_PAGE_DECODED_SIZE_MAX since all Huffman
    # compressed code pages are max HUFFMAN_PAGE_DECODED_SIZE_MAX bytes when uncompressed;
    # target_code_object_entry.size (remember, it means UNCOMPRESSED size for Huffman compressed code objects)
    # is always a multiple of HUFFMAN_PAGE_DECODED_SIZE_MAX.

    num_of_huffman_code_pages = int(target_code_object_entry.size / HUFFMAN_PAGE_DECODED_SIZE_MAX)
    if debug_prints:
        print("read_lut_of_code_object(): there are {0} pages for this code object".format(num_of_huffman_code_pages))
    # and each LUT entry is 4 bytes
    lut = read_lut(from_opened_input_file, num_of_huffman_code_pages * 4, reverse_byte_ordering=True)
    if debug_prints:
        print("read_lut_of_code_object(): lut entries:")
        for lut_entry_dbg in lut:
            print(lut_entry_dbg)

    return lut


def decode_page_from_input_file_i(inp, lut_entry_for_page: LUTentry, outp, offset_into_output, use_relative_seek=True):
    """
    :param inp:    input stream (e.g. result of open()) for reading. Position in the input file doesn't matter.
    :param lut_entry_for_page: the LUT table entry giving information about the page from the input that's to be decoded
    :param outp:   output stream, opened for writing binary data. Position doesn't matter
    :param offset_into_output: the position to seek() into the outp stream prior to writing any data
    :param use_relative_seek: debug reserved (caller: leave at default value for normal operation)

    :return: if error, then < 0
        on success:  the total number of bytes written to the output file during this function run
            (NOTE: this is NOT an absolute position in the output file; rather, relative to the 'offset_into_output'
            parameter that was passed in to the function)
    """
    # typehint this for easier debugging
    found: HuffmanTableEntry

    # relative position trackers for input and output stream, to keep track where I am in the input page and output
    #   "page"
    read_position = 0
    write_position = 0
    # cue up to start writing at the correct position in the output file; This is passed in by the caller explicitly,
    #   as this is expected to be tracked externally. The caller may just decide to write the pages to different files,
    #   or any number of conceivable schemes...
    outp.seek(offset_into_output)

    # how much to refill the bitbuffer (from the input stream) when it runs low on bits (i.e. won't be able to match
    #   the longest_huffman_code_in_bits -sized codes in the table)
    #   This is purely heuristically decided; it may or may not have much effect on decoding speed; I have not done
    #      much testing or benchmarking on it. In any case, don't set it to be LESS THAN longest_huffman_code_in_bits
    #       (or else the bitbuffer won't fill enough in the worst case, and the decoding will end prematurely)
    bitbuffer_topoff_level = longest_huffman_code_in_bits * 10

    if lut_entry_for_page.size == 0:
        # this is the final page, which ends at the end of the file
        # find the end of the file; not strictly needed but helps with debugging (instead could set end as practical
        # infinity, like MAX_LONGINT)
        # inp.seek(0, os.SEEK_END)
        # lut_entry_for_page.size = inp.tell() - lut_entry_for_page.offset
        lut_entry_for_page.size = HUFFMAN_PAGE_DECODED_SIZE_MAX

    # seek to the correct offset for the start of the page
    if use_relative_seek:
        inp.seek(lut_entry_for_page.offset, os.SEEK_CUR)
    else:
        inp.seek(lut_entry_for_page.offset, os.SEEK_SET)

    end_page_position = lut_entry_for_page.offset + lut_entry_for_page.size

    # initial read of the input data:
    # read enough bits to represent the longest huffman code (largest 'rank') in the table
    bytes_for_longest_code = (int(longest_huffman_code_in_bits / 8)
                              + (1 if (longest_huffman_code_in_bits % 8 > 0) else 0))
    # don't read past the end of the file (very unlikely here since I am just starting!)
    bytes_to_read_next: int = int(min(bytes_for_longest_code, end_page_position - read_position))
    in_data = inp.read(bytes_to_read_next)
    read_position += len(in_data)

    # initialize the bitbuffer; initially it has 0 valid bits in it
    valid_bits_in_bitbuffer = 0
    bitbuffer = bitstring.BitArray()

    # ...and now go into a loop, reading and matching codes...
    # The essence of the routine is that the bitbuffer gets bits from the input "added in" (much like a shift-in)
    #   "from the right side" (if you imagine the bitbuffer like a pipe with a left and right opening). There are always
    #   enough bits added in so as to have *at least* enough bits in the bitbuffer to match the Huffman codes in the
    #   table that are the "longest" (i.e. consist of the most bits; I call it "rank" in the code table entries).
    #   (the longest and shortest code in bits is pre-calculated and stored in longest_huffman_code_in_bits, and
    #       shortest_huffman_code_in_bits)
    #   Then the bitbuffer is "slice-copied" "from the left", in a loop, with the slices getting consecutively smaller
    #       each time through the loop, from the longest code possible to the shortest. So e.g. if the longest code was
    #       10 bits in size and the shortest was 8, there would be 3 iterations of the loop, the 1st iter. slicing off
    #       10 bits from [0:10], the 2nd slicing off [0:9] and the 3rd iter. slicing off 8 bits, from [0:8]...and each
    #       slice (which is just another bitbuffer) being checked against the hashtable(*) of all loaded Huffman codes
    #       which was done previously in the script, from the code table input file
    #       (*) (Python: hash table == "dictionary", but not to be confused with the Huffman Code table use of the word
    #           "dictionary" to mean 'decoded data')
    #   When a match is found, the corresponding translation to decoded data (in the code table entry retrieved from
    #       the hashtable), is written to the output, and the size in bits of the match is "invalidated" "from the left"
    #       of the bitbuffer; these bits are subsequently deleted/trimmed-off when the loop reiterates. Effectively,
    #       this reduces the size of the bitbuffer, and if it falls below the threshold of bits, more data is read in
    #       from the input....(and now start reading from the top of this comment block again).
    #   There are TWO termination conditions of the loop (which are considered non-error/valid):
    #   1.  The output reaches HUFFMAN_PAGE_DECODED_SIZE_MAX bytes in size.
    #       By convention/design of this particular variant of Huffman table
    #       encoding, no output page is ever larger than this. As soon as this limit is reached, decoding stops
    #       (the function returns immediately in this case)
    #   2.  The entire input page is read (by the read_position reaching the end_position, as determined by the "size"
    #       of the LUT table entry for the page that was passed in as a parameter).
    #       In this case, the bitbuffer is checked to see if it contains any bits, and if so, if it contains AT LEAST
    #       shortest_huffman_code_in_bits number of bits. If so, then the matching loop is repeated as described above,
    #       except this time, the bitbuffer is not "re-filled" from input data; it simply keeps matching until empty or
    #       no more valid matches can be made. At that point, decoding is considered complete
    #       (Note: even in case #2, the output size is checked, and if it reaches HUFFMAN_PAGE_DECODED_SIZE_MAX,
    #       decoding stops immediately regardless of bits left over in the bitbuffer, if any
    #       (these are considered extraneous/pad/junk bits)
    #
    while read_position < end_page_position:

        new_data_size_in_bits = 8 * len(in_data)
        # prune the bitbuffer to the number of valid bits
        del bitbuffer[0:len(bitbuffer) - valid_bits_in_bitbuffer]
        if len(in_data) > 0:
            # it is safe that this doesn't have an 'else' clause; In case of no new data, the bitbuffer just
            # continues on in its present state, with its existing bits. In fact, this is exactly what happens
            # when the while-loop containing this if-clause exits. Admittedly, it's pretty strange it would happen here
            # as the read_position is still within the page (thus there should be more data!); the caller really
            # shouldn't have called this function if there was no new data. However, it's not *necessarily* a
            # fatal error...if enough bits exist in the bitbuffer to make a match.
            # (and if not, then this function will error out safely anyways; see below, "if not found:" )
            # ...so might as well let it try...
            bitbuffer.append(bitstring.BitArray(bytes=in_data, length=new_data_size_in_bits))
            # print("bitbuffer is up to "+str(len(bitbuffer))+" bits size")
            in_data = []

        valid_bits_in_bitbuffer += new_data_size_in_bits
        longest_code_possible = int(min(longest_huffman_code_in_bits, valid_bits_in_bitbuffer))
        found = None
        nbits_of_hcode = 0
        for nbits_of_hcode in range(longest_code_possible, shortest_huffman_code_in_bits - 1, -1):
            candidate_code = bitstring.ConstBitArray(bitbuffer[0:nbits_of_hcode])
            found = huffman_table.get(candidate_code)
            if found:
                break
        # (end matching loop)
        if not found:
            # error...no code found
            print("error: no matching code for current bitbuffer: " + str(bitbuffer.bin) + " ; aborting.")
            return -1
        # else...
        # a code was found.
        dcode_to_write = found.dict2_value if lut_entry_for_page.dictionary_selector == 1 else found.dict1_value
        outp.write(dcode_to_write)
        write_position += len(dcode_to_write)
        if write_position >= HUFFMAN_PAGE_DECODED_SIZE_MAX:
            # this is the page limit...exit (not an error)
            return write_position
        # it's nbits_of_hcode in size, so this consumes nbits_of_hcode of bits in the bitbuffer
        # ===> denote that fact by decreasing the valid_bits_in_bitbuffer var
        valid_bits_in_bitbuffer -= nbits_of_hcode

        if valid_bits_in_bitbuffer < longest_huffman_code_in_bits:
            # check to see if the bitbuffer is "running low" (i.e. won't have enough to match the longest known code)
            # If so, decide how much more to read from the input stream to "top off" the bitbuffer, and read it
            # (the read-in data will be added to the bitbuffer once the loop re-loops)
            bytes_to_read_next = int(bitbuffer_topoff_level / 8) + (1 if bitbuffer_topoff_level % 8 > 0 else 0)
            # ...but fix-up this value so that the read doesn't go past the end of the page from the input...
            bytes_to_read_next = int(min(bytes_to_read_next, end_page_position - read_position))
            # now that that's figured out, actually read in the data and then update the read_position tracking var
            in_data = inp.read(bytes_to_read_next)
            read_position += len(in_data)
        else:
            # still O.k. in the bitbuffer...plenty of bits left to do matching; no need to go read more just yet
            # ((re)set these variables for safety and consistency for the next loop iteration)
            bytes_to_read_next = 0
            in_data = []
    # (end while loop ; while more bytes to read in the current page of coded data)

    # reached here because there are no more bytes to read from the input...check to see if there is anything left
    # in the bitbuffer. If there is, then attempt matches until either: 1. nothing matches or
    # 2. there are < shortest_huffman_code_in_bits left in the bitbuffer (in which case 1. will apply as well)

    # prune the bitbuffer to the number of valid bits (if already pruned, nothing bad will happen)
    del bitbuffer[0:len(bitbuffer) - valid_bits_in_bitbuffer]
    # start another loop like the file reading one above, but this time the loop just matches the bits already in the
    #   bitbuffer, and it doesn't refill them from an input stream. As before, every match "takes out" bits, and the
    #   bitbuffer gets smaller. Once a match can no longer be made with any of the known Huffman codes in the table,
    #   the loop is complete and the function is done
    while len(bitbuffer) >= shortest_huffman_code_in_bits:
        # prune the bitbuffer to the number of valid bits
        del bitbuffer[0:len(bitbuffer) - valid_bits_in_bitbuffer]
        longest_code_possible = int(min(longest_huffman_code_in_bits, valid_bits_in_bitbuffer))
        found = None
        nbits_of_hcode = 0
        for nbits_of_hcode in range(longest_code_possible, shortest_huffman_code_in_bits - 1, -1):
            candidate_code = bitstring.ConstBitArray(bitbuffer[0:nbits_of_hcode])
            found = huffman_table.get(candidate_code)
            if found:
                break
        # (end matching loop)
        if found:
            dcode_to_write = found.dict2_value if lut_entry_for_page.dictionary_selector == 1 else found.dict1_value
            outp.write(dcode_to_write)
            write_position += len(dcode_to_write)
            if write_position >= HUFFMAN_PAGE_DECODED_SIZE_MAX:
                # this is the page limit...exit (not an error)
                return write_position
            # it's nbits_of_hcode in size, so this consumes nbits_of_hcode of bits in the bitbuffer
            # ===> denote that fact by decreasing the valid_bits_in_bitbuffer var
            valid_bits_in_bitbuffer -= nbits_of_hcode
        else:
            # error...no code found, so this is the end. clear the bitbuffer
            bitbuffer.clear()
            valid_bits_in_bitbuffer = 0
    # (end while depleting all the bits left in the bitbuffer through matching)

    # return the total number of bytes written to the output file during this function run
    # (NOTE: this is NOT an absolute position in the output file; rather, relative to the 'offset_into_output'
    #   parameter that was passed in to the function)
    return write_position


def decode_page_from_input_file(input_file_fqpn, lut_entry_for_page: LUTentry, output_file_fqpn, offset_into_output):
    """
    Parameters:
    :param input_file_fqpn:   the fully-qualified-path-and-name (fqpn) of the file containing the compressed page
            of data
    :param lut_entry_for_page: the LUT table entry giving information about the page from the input that is
            to be decoded
    :param output_file_fqpn:   the fully-qualified-path-and-name (fqpn) of the file where decoded/decompressed
            data should be written
    :param offset_into_output: the position to seek() into the outp stream prior to writing any data

    :return: if error, then < 0
        on success:  the total number of bytes written to the output file during this function run
            (NOTE: this is NOT an absolute position in the output file; rather, relative to the 'offset_into_output'
            parameter that was passed in to the function)

    This function is a wrapper for the "internal" function decode_page_from_input_file_i(...), which takes care of
        opening the input and output streams to the files specified by the parameters, and takes care of closing those
        streams (no matter how the internal function exits).
        (More error handling or input/output redirection could be done here without disturbing/modifying
        the internal function)
    """

    inp = open(input_file_fqpn, "rb")
    if offset_into_output == 0:
        outp = open(output_file_fqpn, "wb")
    else:
        print("appending to output file at position 0x{0:08x} ({0})".format(
            offset_into_output))
        outp = open(output_file_fqpn, "ab")

    result_code = decode_page_from_input_file_i(inp, lut_entry_for_page, outp, offset_into_output)
    inp.close()
    outp.close()
    return result_code


# ###### ---------------------- main helpers ----------------------------------------------------------------- ###### #


def main_run_for_individual_compressed_file_input(output_file_fqpn: str, input_file_fqpn: str,
                                                  lut_file_input_fqpn: str):
    print()
    lut_entry: LUTentry
    LUT = read_lut_file(lut_file_input_fqpn)
    for lut_entry in LUT:
        print(lut_entry)

    print()
    output_write_position = 0
    for index, lut_entry in enumerate(LUT):
        print("decoding page " + str(index + 1) + " (of " + str(len(LUT)) + ") at offset 0x{0:08x} ({0})".format(
            lut_entry.offset))
        result = decode_page_from_input_file(input_file_fqpn, lut_entry, output_file_fqpn, output_write_position)
        if result < 0:
            print("error writing to output file; aborting. (leaving the partial output file intact)")
            break
        output_write_position += result


def main_run_for_packaged_compressed_file_input(output_dir_fqpn: str, input_file_fqpn_or_handle: str,
                                                extract_only_objects_named=None, file_table_location: int = -1):
    # find the first FPT
    if file_table_location < 0:
        if isinstance(input_file_fqpn_or_handle, str):
            found_first_fpt_start = find_fpt_in_file_fqpn(input_file_fqpn_or_handle)
            if not found_first_fpt_start:
                print("Error: input file {0} doesn't seem to contain a file table. Exiting"
                      .format(input_file_fqpn_or_handle))
                return
        else:
            found_first_fpt_start = find_fpt_in_opened_file(input_file_fqpn_or_handle)

        if not found_first_fpt_start:
            print("Error: input file doesn't seem to contain a file table. Exiting")
            return

    file_table_location = found_first_fpt_start[0]
    print("(Using file table (FPT) location: 0x{0:08x} ({0}) )".format(file_table_location))
    if isinstance(input_file_fqpn_or_handle, str):
        file_input = open(input_file_fqpn_or_handle, "rb")
    else:
        file_input = input_file_fqpn_or_handle

    code_partition_descriptors = get_all_cdt(file_input, file_table_location)
    if code_partition_descriptors is None:
        print("There were no code partitions discovered in the input file. (Perhaps the auto-detected file table "
              "location is wrong? try running with \"find filetable\" command-line argument). Exiting")
        return

    decoded_binaries_by_abs_offset = {}
    for code_partition_descriptor in code_partition_descriptors:
        subdir_fqpn = output_dir_fqpn + os.sep + code_partition_descriptor.name + os.sep
        os.makedirs(subdir_fqpn, exist_ok=True)
        print("\nNow within code partition {0}:".format(code_partition_descriptor.name))
        code_object_entries = get_huffman_compressed_code_objects_in_code_partition(file_input,
                                                                                    code_partition_descriptor)
        if code_object_entries is None:
            print("There were no code objects discovered within the code partition/directory. Exiting")
            return

        for code_object_entry in code_object_entries:
            print("processing code object \'{0}\' page lut...".format(code_object_entry.name))
            code_object_lut = read_lut_of_code_object(file_input, code_object_entry)

            if extract_only_objects_named and (code_object_entry.name not in extract_only_objects_named):
                print("Skipping {0}.{1}, as it is not in the list of specified exclusive names to extract"
                      .format(code_object_entry.in_partition.name, code_object_entry.name))
                continue

            # mark the beginning of the code object in the file
            code_object_position_start = file_input.tell()

            output_write_position = 0
            output_fqpn_for_code_object = subdir_fqpn + code_object_entry.name + ".decoded"

            # check to see if this code object is an alias to something already decoded. If so, try and make a symlink
            # and skip actual decoding, and print a message as to what was done; if no symlinks are available
            # (i.e. on Windows) then the symlink attempt will just silently fail (and all you have is the print message
            # to inform as to what happened)
            if code_object_position_start in decoded_binaries_by_abs_offset:
                print("Code object known in this partition as \'{0}\' has previously been decoded to {1}"
                      .format(code_object_entry.name, decoded_binaries_by_abs_offset[code_object_position_start]))
                # try symlinking
                try:
                    os.symlink(decoded_binaries_by_abs_offset[code_object_position_start], output_fqpn_for_code_object)
                except:
                    print("Warn: no symlink possible")
                continue
            print("Writing code object named \'{0}\' to {1}...".format(code_object_entry.name,
                                                                       output_fqpn_for_code_object))
            outp = open(output_fqpn_for_code_object, "wb")
            decode_result = 0
            for index, lut_entry in enumerate(code_object_lut):
                print("decoding page " + str(index + 1) + " (of " + str(
                    len(code_object_lut)) + ") at offset 0x{0:08x} ({0})".format(
                    lut_entry.offset))
                file_input.seek(code_object_position_start, os.SEEK_SET)
                decode_result = decode_page_from_input_file_i(file_input, lut_entry,
                                                              outp, output_write_position)
                if decode_result < 0:
                    print("error writing to output file; aborting. (leaving the partial output file intact)")
                    break
                output_write_position += decode_result
            print("Done writing code object named \'{0}\' to {1}".format(code_object_entry.name,
                                                                         output_fqpn_for_code_object))
            outp.close()
            if decode_result >= 0:
                # make a note of this binary output file, keyed on its absolute offset start position in the input file;
                #  This is to avoid decompressing the same object multiple times, as it seems sometimes different
                #  code partitions will have the same binary 'aliased'
                decoded_binaries_by_abs_offset[code_object_position_start] = output_fqpn_for_code_object

        print("Leaving code partition {0}".format(code_partition_descriptor.name))
    file_input.close()


def main_run_find_filetable(input_file_fqpn: str):
    # start at the beginning of the file
    found_position = find_fpt_in_file_fqpn(input_file_fqpn, 0)
    while found_position:
        print("Found possible FPT start at offset 0x{0:08x} ({0}): number of entries: {1}, header version: 0x{2:02x} "
              ", entry version 0x{3:02x}".format(found_position[0],
                                                 found_position[1], found_position[2], found_position[3]))
        found_position = find_fpt_in_file_fqpn(input_file_fqpn, found_position[0] + 1)


# ############################ main run ###############################################################################

if __name__ == '__main__':
    print("This module is not runnable in this way; please refer to documentation related to this project")
