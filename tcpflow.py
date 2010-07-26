from tcppacket import TCPPacket
import tcpseq
from tcpseq import lt, lte, gt, gte

class TCPFlowError(Exception):
    pass

class TCPFlow:
    '''assembles a series of tcp packets into streams of the actual data
    sent.

    Includes forward data (sent) and reverse data (received), from the
    perspective of the SYN-sender.'''
    def __init__(self, packets):
        '''assembles the series. packets is a list of TCPPacket's from the same
        socket. They should be in order of transmission, otherwise there will
        probably be bugs.'''
        self.packets = packets
        #reference point for determining flow direction
        self.socket = self.packets[0].socket
        # grab handshake, if possible
        # discover direction, etc.
        # synthesize forward data, backwards data
        self.forward_packets = [pkt for pkt in self.packets if self.samedir(pkt)]
        self.reverse_packets = [pkt for pkt in self.packets if not self.samedir(pkt)]
        self.forward_data, self.forward_logger = self.assemble_stream(self.forward_packets)
        self.reverse_data, self.reverse_logger = self.assemble_stream(self.reverse_packets)
        # calculate statistics?

    def assemble_stream(self, packets):
        '''does the actual stitching of the passed packets into data.
        packets = [TCPPacket]
        arrival_logger = TCPDataArrivalLogger
        
        returns the stitched data'''
        # store tuples of format: ((seq_begin, seq_end), data_str, arrival_logger)
        # when a new packet's data overlaps with one, pull that out, merge
        # them, and replace it.
        def merge(old, new):
            '''
            merges the two data tuples together, if they overlap, and
            returns the new data tuple.
            
            old = data tuple ((seq_begin, seq_end), data_str, arrival_logger)
            new = TCPPacket
            '''
            oldseq = old[0]
            newseq = (new.start_seq, new.end_seq)
            # get the data out of the tuple so we can modify it
            new_seq_start = old[0][0]
            new_seq_end = old[0][1]
            newdata = old[1]
            arrival_logger = old[2]
            # see where the new data is, if any
            # hanging-off-front-edge and hanging-off-back-edge cases are designed to be independent
            # if there's new data hanging off the front edge of the old data
            if lt(newseq[0], oldseq[0]) and lte(oldseq[0], newseq[1]):
                # add on front data
                new_data_length = tcpseq.subtract(oldseq[0], newseq[0])
                newdata = new.data[:new_data_length] + newdata # slice out just new data, tack it on front
                new_seq_start = newseq[0]
                arrival_logger.add(newseq[0], new)
            # if there's new data hanging off the back edge...
            if lte(newseq[0], oldseq[1]) and lt(oldseq[1], newseq[1]):
                #add on back data
                new_data_length = tcpseq.subtract(newseq[1], oldseq[0])
                # wrong back_seq_start = newseq[1] - new_data_length # the first sequence number of the new data on the back end
                newdata += new.data[-new_data_length:] # slice out the back of the new data
                new_seq_end += new_data_length
                arrival_logger.add(back_seq_start, new)
            return ((new_seq_start, new_seq_end), newdata, arrival_logger)
        # real start of merge
        stream_segments = [] # the list of data tuples, pieces of the TCP stream. Sorry for the name collision.
        for pkt in packets:
            all_new = True # whether pkt is all new data (needs a new segment, assumed true until proven false)
            for i, olddata in enumerate(stream_segments):
                merged = merge(olddata, pkt)
                if merged:
                    stream_segments[i] = merged #replace old segment with merged one
                    all_new = False
                    break
            # now we've looked through all the existing data
            if all_new: # if we need to make a new packet
                # make a new data segment
                newlogger = TCPDataArrivalLogger()
                newlogger.add(pkt.start_seq, pkt)
                stream_segments.append( ((pkt.start_seq, pkt.end_seq), pkt.data, newlogger) )
        # now all packets are accounted for
        # for now, just return the data out of the first tuple
        num_segments = len(stream_segments)
        if not num_segments:
            raise RuntimeError('TCPFlow.assemble_stream: no data segments')
        else:
            return stream_segments[0][1], stream_segments[0][2]
    
    def samedir(self, pkt):
        '''returns whether the packet is in the same direction as the canonic
        direction of the flow.'''
        src, dst = self.socket
        if pkt.socket == (src,dst):
            return True
        elif pkt.socket == (dst, src):
            return False
        else:
            raise TCPFlowError('In TCPFlow.samedir, found a packet that is from the wrong socket')

class TCPDataArrivalLogger:
    '''
    Keeps track of when TCP data first arrives. does this by storing a
    list/set/whatever of tuples (sequence_number, packet), where sequence_number
    is the first sequence number of the *new* data in packet.
    
    This information, along with the beginning and end sequence numbers of the
    data, allows you to find the packet in which a given sequence number of
    data first arrived, by finding the first number less than the given
    sequence number and then grabbing the associated packet.
    
    This class must be created on a per-buffer basis, and merged whenever the
    buffers are merged.
    '''
    def __init__(self):
        '''Initializes the requisite internal data structure.'''
        self.list = []
    def add(self, sequence_number, pkt):
        '''adds a sequence-number/packet pair to the data.'''
        pass
    def find_packet(self, sequence_number):
        raise NotImplementedError('finding packets by sequence number is not yet fully supported')
        