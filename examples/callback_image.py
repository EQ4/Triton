
from triton import *

# Output
#
# $ ./triton ./examples/callback_image.py ./samples/ir_test_suite/ir
# ----------
# Image path:  /dir/Triton/samples/ir_test_suite/ir
# Image base:  0x400000L
# Image size:  2101312
# ----------
# Image path:  /lib64/ld-linux-x86-64.so.2
# Image base:  0x7fb9a14d9000L
# Image size:  2236744
# ----------
# Image path:  /lib64/libc.so.6
# Image base:  0x7fb98b739000L
# Image size:  3766680


def image(imagePath, imageBase, imageSize):
    print '----------'
    print 'Image path: ', imagePath
    print 'Image base: ', hex(imageBase)
    print 'Image size: ', imageSize


if __name__ == '__main__':

    # Start the symbolic analysis from the 'main' function
    startAnalysisFromSymbol('main')

    # Add a callback.
    addCallback(image, IDREF.CALLBACK.IMAGE_LOAD)

    # Run the instrumentation - Never returns
    runProgram()

